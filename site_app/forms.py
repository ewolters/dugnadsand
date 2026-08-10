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

    def __init__(self, *args, **kwargs):
        """Limit the project list to open projects in this organization.

        RLS already scopes the queryset to the tenant. This narrows it further
        to projects still running, so a form cannot quietly file new work under
        something that finished.
        """
        super().__init__(*args, **kwargs)
        from .models import Project

        self.fields["project"].queryset = Project.objects.filter(open=True)
        self.fields["project"].empty_label = "Not part of anything"

    class Meta:
        from .models import Posting

        model = Posting
        fields = ("kind", "description", "project", "needed_by", "hours_cap")
        labels = {
            "kind": "Are you offering something, or asking for something",
            "description": "In your own words",
            "project": "Part of something ongoing (optional)",
            "needed_by": "Is there a date it stops being useful (optional)",
            "hours_cap": "Roughly how many hours (optional)",
        }
        help_texts = {
            "kind": "Asking costs nothing and proves nothing. Nothing here "
                    "totals what you have given, and nothing consults it.",
            "project": "Only a place to gather related postings. Leaving it "
                       "blank is the normal case.",
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


class ProjectForm(forms.ModelForm):
    """A name and a description. The absences are the design — see the model.

    No owner field, no status, no target date, no budget, no approval. If a
    field is being added here, check it is a fact about the WORK and not a duty
    somebody now owes.
    """

    class Meta:
        from .models import Project

        model = Project
        fields = ("name", "description")
        labels = {
            "name": "What is it called",
            "description": "What is it, in your own words",
        }
        help_texts = {
            "description": "Who it is for, what it needs, how long it might run. "
                           "Nobody is put in charge of it by writing this down.",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}


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


class WarehouseForm(forms.ModelForm):
    """A place somebody keeps things. An address and who to ask.

    No capacity, no utilisation, no cost per pallet. This is an index of
    somebody else's barn, not a warehouse management system.
    """

    class Meta:
        from .models import Warehouse

        model = Warehouse
        fields = ("name", "address", "notes")
        labels = {
            "name": "What to call it",
            "address": "Where it is, and how to get in",
            "notes": "Anything a person turning up should know (optional)",
        }
        help_texts = {
            "address": "Write it however you would tell a neighbour. "
                       "\u201cSecond barn, gate code 4412\u201d beats a postal address.",
        }
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class StockLineForm(forms.Form):
    """Something available. Described, counted, and never priced.

    There is no value field and none may be added. A figure here would be an
    appraisal of donated property produced by a platform about a donor — see
    no-material-valuation in policy/manifest.toml.
    """

    description = forms.CharField(
        max_length=2000, widget=forms.Textarea(attrs={"rows": 3}),
        label="What it is, in your own words")
    quantity = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
        label="How much")
    unit = forms.CharField(
        max_length=40, label="Counted in what",
        help_text="Board-feet, pallets, cases, metres \u2014 whatever you actually "
                  "count it in.")


class SendMaterialForm(forms.Form):
    """Where material is going: onto a project's list, or somewhere written down.

    The need picker is the payoff of having a warehouse and bills of material
    in the same system — pick one and the manifest and the project tell a
    single story instead of two that have to be reconciled by hand.
    """

    need = forms.ModelChoiceField(
        queryset=None, required=False, label="Against a project's list (optional)",
        empty_label="Somewhere else \u2014 write it below")
    quantity = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
        label="How much is going")
    destination = forms.CharField(
        max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 2}),
        label="Where it is going",
        help_text="A person, a site, an organization \u2014 whatever will make sense "
                  "to whoever signs for it. Leave blank if you picked a list above.")

    def __init__(self, *args, line=None, **kwargs):
        """Offer only needs counted in the SAME UNIT as this stock.

        The same rule the pairing page runs on, and for the same reason: a unit
        is a word a member typed, so matching equal ones compares two facts.
        Offering every open need regardless of unit would invite somebody to
        book 200 board-feet against a line measured in pallets, and the
        arithmetic underneath would be nonsense nobody could see.
        """
        super().__init__(*args, **kwargs)
        from .models import MaterialNeed

        field = self.fields["need"]
        if line is None:
            field.queryset = MaterialNeed.objects.none()
            return

        candidates = (MaterialNeed.objects
                      .filter(project__open=True, unit__iexact=line.unit.strip())
                      .select_related("project").prefetch_related("given"))
        # remaining is a property, so the outstanding filter happens here.
        field.queryset = MaterialNeed.objects.filter(
            pk__in=[n.pk for n in candidates if n.remaining > 0])
        field.label_from_instance = (
            lambda n: f"{n.project.name} — {n.description[:60]} "
                      f"({n.remaining} {n.unit} still needed)")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("need") and not (cleaned.get("destination") or "").strip():
            self.add_error(
                "destination",
                "Say where it is going, or pick a project's list above.")
        return cleaned


class MaterialNeedForm(forms.Form):
    """A line on a bill of materials. What, and how much.

    No value field, and none may be added: an estimate of donated property is
    a §170 appraisal produced by a platform about a donor. No hours field
    either — an equivalence between material and labour is an exchange rate.
    """

    description = forms.CharField(
        max_length=2000, widget=forms.Textarea(attrs={"rows": 2}),
        label="What is needed")
    quantity = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
        label="How much")
    unit = forms.CharField(max_length=40, label="Counted in what")


class MaterialGivenForm(forms.Form):
    quantity = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
        label="How much arrived")
    note = forms.CharField(
        max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 2}),
        label="Anything worth remembering (optional)")
