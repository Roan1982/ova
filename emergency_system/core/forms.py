from django import forms
from .models import Emergency

class EmergencyForm(forms.ModelForm):
    class Meta:
        model = Emergency
        fields = ['description', 'address']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'description': 'Descripción',
            'address': 'Dirección',
        }
