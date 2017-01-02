import requests.exceptions
import stripe

from mailchimp3 import MailChimp

from django.core.urlresolvers import reverse
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render

from job_board.forms import ContactForm, CssUserCreationForm, SubscribeForm
from job_board.models.job import Job
from job_board.models.site_config import SiteConfig
from utils.misc import send_mail_with_helper


def charge(request):
    if request.method == 'POST':
        site = get_current_site(request)
        sc = SiteConfig.objects.filter(site=site).first()
        stripe.api_key = sc.stripe_secret_key
        job = get_object_or_404(
                  Job,
                  pk=request.POST['job_id'],
                  site_id=site.id,
                  user_id=request.user.id
              )

        token = request.POST['stripeToken']

        try:
            desc = '%s Job Posting (%s://%s/jobs/%s)' % (
                       site.name, sc.protocol, site.domain, job.id
                   )
            charge = stripe.Charge.create(
                source=token,
                amount=sc.price_in_cents(),
                currency='usd',
                description=desc,
                receipt_email=request.user.email
            )
        # NOTE: With checkout.js, it seems that all the error handling is
        #       handled on the front-end, so perhaps we do not need to worry
        #       about handling this exception.
        except stripe.error.CardError as e:
            body = e.json_body
            err = body['error']
            messages.error(request, err['message'])
            return HttpResponseRedirect(reverse('jobs_show', args=(job.id,)))
        else:
            if charge['paid']:
                job.activate()
                messages.success(
                    request,
                    ("Thank you, your payment of $%s has been received and "
                     "your job is now active" % sc.price)
                )

        return HttpResponseRedirect(reverse('jobs_show', args=(job.id,)))


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            site = get_current_site(request)
            sc = SiteConfig.objects.filter(site=site).first()
            cd = form.cleaned_data
            # re-tag subject to make it more identifiable
            cd['subject'] = "[%s] %s" % (site.name.upper(), cd['subject'])
            send_mail_with_helper(
                cd['subject'],
                cd['message'],
                cd['email'],
                [sc.admin_email]
            )

            messages.success(
                request,
                "Thank you for your message, "
                "we'll be back in touch as soon as possible"
            )

            return HttpResponseRedirect(reverse('jobs_index'))
    else:
        form = ContactForm()

    title = 'Contact Us'
    return render(request, "job_board/contact.html", {
        'form': form, 'title': title,
    })


def register(request):
    if request.method == 'POST':
        form = CssUserCreationForm(request.POST)
        if form.is_valid():
            form.save()

            messages.success(
                request,
                'Your account has been successfully created, '
                'please log in to continue'
            )

            return HttpResponseRedirect(reverse('jobs_index'))
    else:
        form = CssUserCreationForm()

    title = 'Register'
    return render(request, "registration/register.html", {
        'form': form, 'title': title
    })


def subscribe(request):
    site = get_current_site(request)
    if (request.method == 'POST' and site.siteconfig.mailchimp_username and
            site.siteconfig.mailchimp_api_key and
            site.siteconfig.mailchimp_list_id):
        form = SubscribeForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            client = MailChimp(
                         site.siteconfig.mailchimp_username,
                         site.siteconfig.mailchimp_api_key
                     )

            try:
                client.lists.members.get(
                    site.siteconfig.mailchimp_list_id,
                    cd['email']
                )
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    client.lists.members.create(
                        site.siteconfig.mailchimp_list_id,
                        {
                            'email_address': cd['email'],
                            'status': 'pending',
                            'merge_fields': {
                                'FNAME': cd['fname']
                            },
                        }
                    )
                    messages.success(
                        request,
                        'Thanks, you have been subscribed to our list!'
                    )
                else:
                    messages.failure(
                        request,
                        'Something went wrong, please try again'
                    )
            else:
                messages.warning(
                    request,
                    'Looks like this address is already subscribed to '
                    'our list!'
                )
        else:
            messages.warning(
                request,
                'There was a problem with the form, please try again'
            )

    return HttpResponseRedirect(reverse('jobs_index'))
