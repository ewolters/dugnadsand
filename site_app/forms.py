from decimal import Decimal

from django import forms


class Branded:
    """House defaults for every form on the site.

    label_suffix is dropped. Django appends a colon to every label, so a
    carefully written "Where to gather, if that is somewhere else (optional)"
    renders as "...(optional):" — a trailing colon after a closing bracket,
    on every field, on every page. It reads as unfinished because nobody
    chose it.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)


class StampedPublicForm:
    """The "you must have loaded the page" check, without a cookie.

    Extracted from ContactForm when the application ingress needed the same
    defence. Both are anonymous POSTs where CSRF protects nothing -- there is
    no session to ride -- but where the incidental property of CSRF, that a
    blind POST is refused, is worth keeping.

    A subclass sets its own STAMP_SALT so a stamp minted for one form cannot
    be replayed against the other.
    """

    STAMP_SALT = "dugnadsand.public"
    MIN_SECONDS = 2
    MAX_SECONDS = 60 * 60 * 24

    STALE = "This form went stale. Reload the page and send it again."

    @classmethod
    def stamp(cls):
        """A fresh signed timestamp, for a form about to be rendered."""
        import time

        from django.core import signing

        return signing.Signer(salt=cls.STAMP_SALT).sign(str(int(time.time())))

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("")
        return ""

    def _check_stamp(self):
        import time

        from django.core import signing

        raw = (self.data.get("t") or "").strip()
        if not raw:
            raise forms.ValidationError(self.STALE)
        try:
            issued = int(signing.Signer(salt=self.STAMP_SALT).unsign(raw))
        except (signing.BadSignature, ValueError):
            raise forms.ValidationError(self.STALE)

        age = int(time.time()) - issued
        if age > self.MAX_SECONDS or age < self.MIN_SECONDS:
            # One wording for both. Telling a script it was too QUICK tells it
            # exactly what to change; a person only needs to know to reload.
            raise forms.ValidationError(self.STALE)

    def clean(self):
        """The stamp check lands as a NON-FIELD error on purpose.

        `t` is hidden, and templates render errors for the visible fields and
        for non-field errors -- so an error attached to `t` redisplayed the
        form with no explanation whatsoever. Somebody would press send, watch
        the page reload unchanged, and have no idea why.
        """
        cleaned = super().clean()
        try:
            self._check_stamp()
        except forms.ValidationError as exc:
            self.add_error(None, exc)
        return cleaned


class ContactForm(Branded, StampedPublicForm, forms.Form):
    """Front-page contact form. Delivered by kjerne_platform.email.

    CSRF-EXEMPT, AND THIS IS WHAT REPLACES IT.

    A token on an anonymous form protects nothing — the attack CSRF prevents
    is riding a logged-in session, and anybody wanting to send mail through
    here would POST from their own machine. What it did do, incidentally, was
    turn away bots that blind-POST without ever fetching the page. And it
    turned away real people whose browsers do not return cookies, which is
    what actually happened on 2026-08-11.

    So the "you must have loaded the page" property is kept and the cookie is
    dropped: a signed timestamp in the form. It proves the form came from a
    page this server rendered, and when — no cookie, no session, works for
    somebody with everything blocked.

    Rejecting too FAST as well as too old is the part that catches scripts. A
    person typing a name, an address and a sentence takes longer than two
    seconds; something that fetches and immediately posts does not.
    """

    STAMP_SALT = "dugnadsand.contact"
    MIN_SECONDS = 2          # faster than a person can fill three fields
    MAX_SECONDS = 60 * 60 * 24

    name = forms.CharField(max_length=120)
    email = forms.EmailField(max_length=254)
    message = forms.CharField(max_length=4000, widget=forms.Textarea)

    # Bots fill every field they find. People never see this one.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    # Signed server-side, so it cannot be forged or replayed past its window.
    t = forms.CharField(required=False, widget=forms.HiddenInput)


class MemberLoginForm(Branded, forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)


class PostingForm(Branded, forms.ModelForm):
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
        from .models import Posting, Project

        self.fields["project"].queryset = Project.objects.filter(open=True)
        self.fields["project"].empty_label = "Not part of anything"

        # Said as a person would say it, at the FORM level. The model's
        # choices are untouched: editing those needs a migration, and the
        # stored values are what the rest of the system reads.
        self.fields["kind"].choices = [
            (Posting.OFFER, "I'm offering something"),
            (Posting.NEED, "I'm asking for something"),
        ]
        self.fields["description"].widget.attrs.update({
            "placeholder": "What is it? Write it however you would say it.",
            "autofocus": "autofocus",
        })

    class Meta:
        from .models import Posting

        model = Posting
        fields = ("kind", "description", "project", "needed_by", "hours_cap")
        labels = {
            "kind": "Which is it",
            "description": "In your own words",
            "project": "Part of something ongoing",
            "needed_by": "Needed by",
            "hours_cap": "Roughly how many hours",
        }
        help_texts = {
            "kind": "",
            "project": "Only a place to gather related postings.",
            "needed_by": "A ride on Thursday and a fence sometime this year are "
                         "different things. Blank means no rush.",
            "hours_cap": "A ceiling, never a floor. Whoever takes this on can "
                         "stop before it, any time, and nothing is recorded.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "needed_by": forms.DateInput(attrs={"type": "date"}),
            "kind": forms.RadioSelect,
        }


class ProjectForm(Branded, forms.ModelForm):
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
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "What is it called?", "autofocus": "autofocus"}),
            "description": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Who it is for, what it needs, how long it might "
                               "run. Nobody is put in charge of it by writing "
                               "this down."}),
        }


class ContributionForm(Branded, forms.Form):
    """Hours given, and a note. No money field exists and none may be added."""

    hours = forms.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0.01"),
                               label="Hours given")
    note = forms.CharField(max_length=2000, required=False,
                           widget=forms.Textarea(attrs={"rows": 3}),
                           label="Anything worth remembering (optional)")


class AddMemberForm(Branded, forms.Form):
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


class WarehouseForm(Branded, forms.ModelForm):
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


class StockLineForm(Branded, forms.Form):
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


class SendMaterialForm(Branded, forms.Form):
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


class MaterialNeedForm(Branded, forms.Form):
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


class MaterialGivenForm(Branded, forms.Form):
    quantity = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
        label="How much arrived")
    note = forms.CharField(
        max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 2}),
        label="Anything worth remembering (optional)")


class WorkDayForm(Branded, forms.ModelForm):
    """A day, a place, a time. Nothing about who is expected.

    There is no attendees field, no headcount and no capacity, and none may be
    added — see WorkDay's docstring. People give time by claiming postings, on
    a work day exactly as on any other.
    """

    class Meta:
        from .models import WorkDay

        model = WorkDay
        fields = ("name", "description", "project", "starts_at", "ends_at",
                  "place", "muster")
        labels = {
            "name": "What to call it",
            "description": "What the day is for, and what to bring",
            "project": "Part of something ongoing (optional)",
            "starts_at": "Starts",
            "ends_at": "Ends (optional)",
            "place": "Where",
            "muster": "Where to gather, if that is somewhere else (optional)",
        }
        help_texts = {
            "place": "Write it however you would tell a neighbour. "
                     "“The Cedar Lane put-in, park on the grass by the gate” "
                     "beats a postal address.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "place": forms.Textarea(attrs={"rows": 3}),
            "muster": forms.Textarea(attrs={"rows": 2}),
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Project

        self.fields["project"].queryset = Project.objects.filter(open=True)
        self.fields["project"].empty_label = "On its own"
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]

    def clean(self):
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_at"), cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", "That is before it starts.")
        return cleaned


class ClearanceForm(Branded, forms.Form):
    """A permission the day needs and does not have yet.

    kind is free text. Every county names things differently, and a shipped
    list of permission types would be a catalog — which this system keeps of
    nothing else either.
    """

    kind = forms.CharField(
        max_length=120, label="What is needed",
        help_text="“River access permit”, “Landowner permission”, "
                  "“Certificate of insurance” — whatever it is called locally.")
    authority = forms.CharField(
        max_length=2000, widget=forms.Textarea(attrs={"rows": 2}),
        label="Who has to say yes")
    note = forms.CharField(
        max_length=4000, required=False, widget=forms.Textarea(attrs={"rows": 2}),
        label="Anything worth writing down (optional)")


class ClearanceObtainedForm(Branded, forms.Form):
    """Somebody said yes. When, and how a person who was not on the call can
    check it.

    Takes no member. Who obtained it goes in the note: a second Member FK on
    that row is the shape of a transfer, and no-exchange refuses it.
    """

    obtained_on = forms.DateField(
        label="When it was given",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    reference = forms.CharField(
        max_length=200, required=False, label="Reference (optional)",
        help_text="A permit number, an email date, the name of whoever said it "
                  "— whatever makes it checkable by somebody else.")
    expires_on = forms.DateField(
        required=False, label="Runs out on (optional)",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Leave blank if it does not expire. A permit for a date does, "
                  "and an expired one blocks the day again.")
    note = forms.CharField(
        max_length=4000, required=False, widget=forms.Textarea(attrs={"rows": 3}),
        label="Note (optional)")

    def clean(self):
        cleaned = super().clean()
        obtained, expires = cleaned.get("obtained_on"), cleaned.get("expires_on")
        if obtained and expires and expires < obtained:
            self.add_error("expires_on", "That is before it was given.")
        return cleaned


class ApplicationForm(Branded, StampedPublicForm, forms.Form):
    """Applying to join the network.

    What is asked for changes with the kind, and clean() enforces it, because
    a business that never entered a licence number should be told so on the
    page rather than becoming an outstanding row somebody chases by email.

    NOTHING HERE ASKS WHAT THE APPLICANT OFFERS, OR HOW GOOD THEY ARE AT IT.
    An electrician proves a licence and insurance. No field rates, tiers or
    describes their work, because a system that graded offers would be
    pricing them.
    """

    STAMP_SALT = "dugnadsand.apply"

    kind = forms.ChoiceField(label="What is applying")
    region = forms.ModelChoiceField(
        queryset=None, required=False, label="Which chapter (optional)",
        empty_label="Not sure, or none covers us yet")

    legal_name = forms.CharField(
        max_length=200, label="Name on the paperwork",
        help_text="The registered name, which is often not the trading name.")
    contact_name = forms.CharField(max_length=200, label="Contact person")
    email = forms.EmailField(max_length=254, label="Email")
    phone = forms.CharField(max_length=60, required=False, label="Phone (optional)")
    locality = forms.CharField(
        max_length=200, required=False, label="Location (optional)")

    statement = forms.CharField(
        max_length=4000, widget=forms.Textarea(attrs={"rows": 5}),
        label="Reason for applying")

    # Businesses and not-for-profits. Required per kind in clean().
    license_authority = forms.CharField(
        max_length=200, required=False, label="Licence issued by")
    license_reference = forms.CharField(
        max_length=200, required=False, label="Licence number")
    license_expires = forms.DateField(
        required=False, label="Licence runs out",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    insurance_authority = forms.CharField(
        max_length=200, required=False, label="Insurer")
    insurance_reference = forms.CharField(
        max_length=200, required=False, label="Policy number")
    insurance_expires = forms.DateField(
        required=False, label="Cover runs out",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    tax_reference = forms.CharField(
        max_length=200, required=False, label="Tax identification number")
    determination_reference = forms.CharField(
        max_length=200, required=False,
        label="IRS determination letter reference")

    agreed = forms.BooleanField(
        required=False,
        label="The statement of operating policy has been read and is agreed")

    website = forms.CharField(required=False, widget=forms.HiddenInput)
    t = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Application, Region

        self.fields["kind"].choices = Application.KINDS
        self.fields["region"].queryset = Region.objects.filter(active=True)

    def clean(self):
        cleaned = super().clean()
        from .models import Application

        kind = cleaned.get("kind")

        if not cleaned.get("agreed"):
            self.add_error(
                "agreed",
                "Agreement to the operating policy is required of every party in "
                "the network.")

        if kind == Application.BUSINESS:
            for field, label in (("license_reference", "licence number"),
                                 ("license_expires", "date the licence runs out"),
                                 ("insurance_reference", "policy number"),
                                 ("insurance_expires", "date the cover runs out"),
                                 ("tax_reference", "tax identification number")):
                if not cleaned.get(field):
                    self.add_error(field, f"A business needs its {label}.")

        if kind == Application.NONPROFIT:
            for field, label in (("determination_reference", "determination letter"),
                                 ("tax_reference", "tax identification number")):
                if not cleaned.get(field):
                    self.add_error(field, f"A not-for-profit needs its {label}.")

        return cleaned

    def credentials(self):
        """What the applicant typed, keyed by the names in REQUIRED."""
        c = self.cleaned_data
        return {
            "Business license": {
                "authority": c.get("license_authority", ""),
                "reference": c.get("license_reference", ""),
                "expires_on": c.get("license_expires")},
            "Certificate of insurance": {
                "authority": c.get("insurance_authority", ""),
                "reference": c.get("insurance_reference", ""),
                "expires_on": c.get("insurance_expires")},
            "Tax identification number": {
                "reference": c.get("tax_reference", "")},
            "IRS determination letter": {
                "reference": c.get("determination_reference", "")},
        }


class MeasureForm(Branded, forms.Form):
    """Something true about the world after the work.

    There is no field for a value and none for hours, and the unit is checked
    in services_packet.check_unit rather than here so the refusal holds for
    every caller — the form is one way in, not the rule.
    """

    label = forms.CharField(
        max_length=200, label="What was measured",
        help_text="“Debris removed”, “Riverbank cleared”, "
                  "“Roofs made watertight”.")
    quantity = forms.DecimalField(max_digits=12, decimal_places=2, label="How much")
    unit = forms.CharField(
        max_length=40, label="Counted in what",
        help_text="Tons, metres, houses, bags — whatever it was actually "
                  "counted in. Not money, and not hours.")
    note = forms.CharField(
        max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 2}),
        label="Anything worth saying about it (optional)")


class PhotoForm(Branded, forms.Form):
    image = forms.FileField(label="Photograph")
    depicts_people = forms.BooleanField(
        required=False, initial=True, label="There are people in this picture",
        help_text="Leave this ticked unless the photograph shows no "
                  "identifiable person. A packet cannot be published while "
                  "anybody in it has not agreed.")
    caption = forms.CharField(
        max_length=300, required=False, label="Caption (optional)",
        help_text="What is happening in it. Naming people is a decision for "
                  "the people in the picture.")


class PacketForm(Branded, forms.Form):
    """The words around the evidence.

    acknowledgements is prose somebody writes, not a generated list. Who a
    community thanks is a human act; generating it would rank people by what
    they gave, which is the score this system exists without.
    """

    title = forms.CharField(max_length=200, label="Title")
    summary = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 6}), max_length=8000,
        label="What happened",
        help_text="Written for somebody who was not there and gave something "
                  "to it.")
    acknowledgements = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 4}), max_length=4000,
        label="Who to thank (optional)",
        help_text="In your own words. Nothing here is generated, and nothing "
                  "is ranked.")


class ConsentForm(Branded, forms.Form):
    """Recording that somebody in a photograph agreed, or did not.

    person is a name typed by whoever asked. Most people at a work party are
    not members, so this is not a picker — and a picker would only cover the
    people the system already knows about, which is the wrong half.
    """

    person = forms.CharField(max_length=200, label="Who is in it")
    given_on = forms.DateField(
        required=False, label="When they agreed",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Leave blank to note that somebody is in the picture before "
                  "they have been asked.")
    how = forms.CharField(
        max_length=120, required=False, label="How (optional)",
        help_text="In person, by message, on a signed form — whatever "
                  "happened.")
    note = forms.CharField(
        max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 2}),
        label="Note (optional)")
