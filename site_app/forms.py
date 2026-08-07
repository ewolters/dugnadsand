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
