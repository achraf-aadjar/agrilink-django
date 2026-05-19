from .models import Farmer


def demo_user(request):
    farmer = Farmer.objects.filter(phone='+221 77 000 00 01').first()
    return {'demo_farmer': farmer}
