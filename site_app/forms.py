from decimal import Decimal

from django import forms


class ContactForm(forms.Form):
    """Front-page contact form. Delivered by kjerne_platform.email."""

    name = forms.CharField(max_length=120)
    email = forms.EmailField(max_length=254)
    message = forms.CharField(max_length=4000, widget=forms.Textarea)

    # Bots fill every field they find. People never see this one.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("")
        return ""


class MemberLoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)


class PostingForm(forms.ModelForm):
    """A direction, free text, and a rough size. That is the entire form.

    No category, no service type, no suggested hours, no rate. Standardised
    options create comparables and comparables create ascertainable value —
    see policy/manifest.toml, no-catalog. If you are here to add a dropdown so
    postings are easier to search, that is exactly the change the manifest
    forbids.
    """

    class Meta:
        from .models import Posting

        model = Posting
        fields = ("kind", "description", "needed_by", "hours_cap")
        labels = {
            "kind": "Are you offering something, or asking for something",
            "description": "In your own words",
            "needed_by": "Is there a date it stops being useful (optional)",
            "hours_cap": "Roughly how many hours (optional)",
        }
        help_texts = {
            "kind": "Asking costs nothing and proves nothing. Nobody can see "
                    "what you have or have not contributed.",
            "needed_by": "A ride on Thursday and a fence sometime this year are "
                         "different things. Leave it blank if there's no rush.",
            "hours_cap": "A ceiling, never a floor. Whoever takes this on can "
                         "stop before it, any time, and nothing is recorded.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "needed_by": forms.DateInput(attrs={"type": "date"}),
            "kind": forms.RadioSelect,
        }


class ContributionForm(forms.Form):
    """Hours given, and a note. No money field exists and none may be added."""

    hours = forms.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0.01"),
                               label="Hours given")
    note = forms.CharField(max_length=2000, required=False,
                           widget=forms.Textarea(attrs={"rows": 3}),
                           label="Anything worth remembering (optional)")


class AddMemberForm(forms.Form):
    """An organizer adding somebody to their own organization.

    No organization field: it is always the organizer's own, taken from the
    request. Posting a choice would be posting a way to get it wrong.
    """

    username = forms.CharField(max_length=150, label="Username they'll sign in with")
    display_name = forms.CharField(max_length=120, label="How they appear to others")
    email = forms.EmailField(
        max_length=254, label="Email",
        help_text="Required. Their second factor is keyed to this address.")
    is_organizer = forms.BooleanField(
        required=False, label="Can add other members",
        help_text="Organizers add people. They get no extra view of the ledger.")
