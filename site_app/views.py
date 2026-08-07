import logging
import os

from django.shortcuts import redirect, render
from kjerne_platform import email, rate_limit

from .forms import ContactForm

logger = logging.getLogger(__name__)

SITE = "dugnadsand"
# Set per deployment; deliberately absent from the repo so no inbox is published.
INBOX = os.environ.get("DUGNADSAND_CONTACT_EMAIL")


def _client_ip(request):
    forwarded = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get(
        "HTTP_X_FORWARDED_FOR", ""
    )
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def index(request):
    if request.method != "POST":
        return render(request, "site_app/index.html", {
            "form": ContactForm(),
            "sent": request.GET.get("sent") == "1",
        })

    form = ContactForm(request.POST)
    if not form.is_valid():
        return render(request, "site_app/index.html", {"form": form, "sent": False})

    # Five a day per address keeps a bored someone from filling the inbox.
    if not rate_limit.check("dugnadsand_contact", _client_ip(request), 5, 86400):
        form.add_error(None, "That's a few too many messages for one day. Try tomorrow.")
        return render(request, "site_app/index.html", {"form": form, "sent": False})

    if not INBOX:
        # Fail loudly in the log rather than quietly dropping someone's message.
        logger.error("DUGNADSAND_CONTACT_EMAIL is unset; contact form cannot deliver.")
        form.add_error(None, "The contact form isn't set up yet. Please try again later.")
        return render(request, "site_app/index.html", {"form": form, "sent": False})

    data = form.cleaned_data
    email.send(
        to=INBOX,
        subject=f"dugnadsand.org — {data['name']}",
        body=f"From: {data['name']} <{data['email']}>\n\n{data['message']}",
        site=SITE,
        reply_to=data["email"],
    )
    # Redirect after post so a refresh doesn't send it a second time.
    return redirect("/?sent=1#say-hello")
