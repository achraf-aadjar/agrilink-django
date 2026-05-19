from .models import Farmer


def current_farmer(request):
    farmer_id = request.session.get('farmer_id')
    if not farmer_id:
        return {'farmer': None}
    farmer = Farmer.objects.filter(id=farmer_id).first()
    return {'farmer': farmer}
