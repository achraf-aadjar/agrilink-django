import json
import random
import hashlib
import requests
from datetime import date, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from django.contrib import messages
from django.db.models import Avg, Sum
from django.db.models.functions import TruncMonth

from .models import Farmer, Listing, CreditApplication, InsurancePolicy, ChatMessage, Offer

REGION_COORDS = {
    'Dakar':       (14.6928, -17.4467),
    'Thiès':       (14.7833, -16.9167),
    'Kaolack':     (14.1524, -16.0726),
    'Ziguinchor':  (12.5603, -16.2719),
    'Saint-Louis': (16.0179, -16.4896),
    'Tambacounda': (13.7707, -13.6673),
    'Fatick':      (14.3392, -16.4115),
    'Louga':       (15.6173, -16.2240),
}

CROPS_CATALOG = [
    {'crop': 'Arachide', 'base': 385, 'emoji': '🥜'},
    {'crop': 'Mil',      'base': 195, 'emoji': '🌾'},
    {'crop': 'Maïs',     'base': 165, 'emoji': '🌽'},
    {'crop': 'Tomate',   'base': 280, 'emoji': '🍅'},
    {'crop': 'Oignon',   'base': 320, 'emoji': '🧅'},
    {'crop': 'Mangue',   'base': 150, 'emoji': '🥭'},
    {'crop': 'Sorgho',   'base': 180, 'emoji': '🌿'},
    {'crop': 'Niébé',    'base': 350, 'emoji': '🫘'},
]

CROPS_EMOJI = {c['crop']: c['emoji'] for c in CROPS_CATALOG}
CROPS_BASE  = {c['crop']: c['base']  for c in CROPS_CATALOG}

IMF_PARTNERS = [
    {'id': 'boa',     'name': 'Bank of Africa',   'logo': '🏦', 'rate': 7.5, 'max_amount': 500000, 'coverage': 'Sénégal · UEMOA'},
    {'id': 'cncas',   'name': 'CNCAS',            'logo': '🌱', 'rate': 6.0, 'max_amount': 300000, 'coverage': 'Agriculture uniquement'},
    {'id': 'pamecas', 'name': 'PAMECAS',          'logo': '🤝', 'rate': 8.0, 'max_amount': 200000, 'coverage': 'Petits producteurs'},
    {'id': 'axa',     'name': 'AXA Microfinance', 'logo': '💼', 'rate': 9.0, 'max_amount': 150000, 'coverage': 'Crédit rapide 24h'},
]

GROQ_SYSTEM_PROMPT = """Tu es un conseiller agronomique expert spécialisé en agriculture ouest-africaine, particulièrement au Sénégal et dans la zone UEMOA.

Tu connais parfaitement :
- Les cultures locales : arachide, mil, maïs, sorgho, fonio, maraîchage, mangue, anacarde, niébé, coton
- Les maladies et ravageurs courants (rosette de l'arachide, mildiou, anthracnose, etc.)
- Les techniques d'irrigation adaptées au Sahel
- La fertilisation organique et minérale
- Le calendrier cultural par région (Kaolack, Ziguinchor, Saint-Louis, Thiès, Tambacounda, etc.)
- Les prix du marché et les filières agricoles UEMOA

Règles :
- Réponds en Français si la question est en Français
- Réponds en Wolof si la question est en Wolof
- Conseils pratiques et concrets pour petits producteurs
- Maximum 400 mots, utilise **bold** pour les points clés"""


# ─── Auth helper ──────────────────────────────────────────────────────────────

def get_current_farmer(request):
    farmer_id = request.session.get('farmer_id')
    if not farmer_id:
        return None
    return Farmer.objects.filter(id=farmer_id).first()


# ─── Market prices (calculated from real listings) ────────────────────────────

def get_market_prices():
    today     = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = []
    for item in CROPS_CATALOG:
        # Real average price from active listings if available
        avg = Listing.objects.filter(
            is_active=True, crop__iexact=item['crop']
        ).aggregate(avg=Avg('price_per_kg'))['avg']
        base = round(avg) if avg else item['base']

        # Apply small deterministic daily variation
        h  = int(hashlib.md5(f"{item['crop']}{today}".encode()).hexdigest()[:8], 16)
        hy = int(hashlib.md5(f"{item['crop']}{yesterday}".encode()).hexdigest()[:8], 16)
        variation  = ((h  % 41) - 20) / 1000
        variation_y = ((hy % 41) - 20) / 1000
        price   = round(base * (1 + variation))
        price_y = round(base * (1 + variation_y))
        change  = round(((price - price_y) / price_y) * 100, 1)
        result.append({'crop': item['crop'], 'price': price, 'change': change, 'emoji': item['emoji']})
    return result


# ─── Revenue bars from real offers ────────────────────────────────────────────

def get_revenue_bars(farmer):
    MONTHS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun',
              'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']
    year = date.today().year
    accepted = (
        Offer.objects
        .filter(listing__farmer=farmer, status='accepted')
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('total'))
    )
    monthly = {o['month'].month: o['total'] for o in accepted}

    bars = [{'month': MONTHS[m - 1], 'revenue': monthly.get(m, 0)} for m in range(1, 13)]
    max_rev = max((b['revenue'] for b in bars), default=1) or 1
    for b in bars:
        b['pct'] = max(4, round((b['revenue'] / max_rev) * 100)) if b['revenue'] else 4
    return bars


# ─── SMS OTP ─────────────────────────────────────────────────────────────────

def send_otp_sms(phone, otp):
    if not settings.TWILIO_ACCOUNT_SID:
        return False
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f"AgriLink — Votre code de connexion : {otp}",
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone,
        )
        return True
    except Exception:
        return False


# ─── Météo ────────────────────────────────────────────────────────────────────

_weather_cache = {}

def get_weather(region):
    cache_key = f"{region}_{date.today().isoformat()}"
    if cache_key in _weather_cache:
        return _weather_cache[cache_key]
    if not settings.OPENWEATHER_API_KEY:
        return None
    lat, lon = REGION_COORDS.get(region, (14.6928, -17.4467))
    try:
        r = requests.get(
            'https://api.openweathermap.org/data/2.5/weather',
            params={'lat': lat, 'lon': lon, 'appid': settings.OPENWEATHER_API_KEY, 'units': 'metric'},
            timeout=5,
        )
        data        = r.json()
        rain_1h     = data.get('rain', {}).get('1h', 0)
        humidity    = data.get('main', {}).get('humidity', 50)
        temp        = data.get('main', {}).get('temp', 30)
        description = data.get('weather', [{}])[0].get('description', '').capitalize()
        rainfall_30d = round(rain_1h * 24 * 30, 1) if rain_1h else round(humidity * 0.3, 1)
        risk_index   = min(100, round((humidity * 0.5) + (max(0, temp - 25) * 2)))
        result = {'rainfall_30d': rainfall_30d, 'risk_index': risk_index,
                  'humidity': humidity, 'temp': temp, 'description': description}
        _weather_cache[cache_key] = result
        return result
    except Exception:
        return None


# ─── Statistiques plateforme ──────────────────────────────────────────────────

def get_platform_stats():
    total_farmers  = Farmer.objects.count()
    total_listings = Listing.objects.filter(is_active=True).count()
    total_offers   = Offer.objects.count()
    total_volume   = Offer.objects.filter(status='accepted').aggregate(v=Sum('total'))['v'] or 0
    return {
        'farmers':  total_farmers,
        'listings': total_listings,
        'offers':   total_offers,
        'volume':   total_volume,
    }


# ─── Landing ─────────────────────────────────────────────────────────────────

def landing(request):
    farmer = get_current_farmer(request)
    if farmer:
        return redirect('dashboard')
    return render(request, 'landing.html', {'stats': get_platform_stats()})


# ─── Auth ────────────────────────────────────────────────────────────────────

def auth(request):
    if get_current_farmer(request):
        return redirect('dashboard')

    if request.method == 'POST':
        step = request.POST.get('step')

        if step == 'otp':
            otp_input    = request.POST.get('otp', '').strip()
            expected_otp = request.session.get('otp_code', '')
            otp_phone    = request.session.get('otp_phone', '')
            if otp_input == expected_otp and otp_phone:
                farmer, created = Farmer.objects.get_or_create(
                    phone=otp_phone,
                    defaults={'name': '', 'region': '', 'crops': [], 'surface': 1.0},
                )
                request.session['farmer_id'] = farmer.id
                del request.session['otp_code']
                del request.session['otp_phone']
                # New farmer with no name → onboarding
                if not farmer.name:
                    return redirect('setup')
                return redirect('dashboard')
            messages.error(request, 'Code incorrect. Réessayez.')
            return render(request, 'auth.html', {
                'step': 'otp',
                'phone': otp_phone,
                'demo_otp': None,
            })

        elif step == 'phone':
            phone = request.POST.get('phone', '').strip()
            if not phone:
                messages.error(request, 'Numéro de téléphone requis.')
                return render(request, 'auth.html', {'step': 'phone'})
            otp = str(random.randint(100000, 999999))
            request.session['otp_code']  = otp
            request.session['otp_phone'] = phone
            sms_sent = send_otp_sms(phone, otp)
            return render(request, 'auth.html', {
                'step': 'otp', 'phone': phone,
                'demo_otp': None if sms_sent else otp,
            })

    return render(request, 'auth.html', {'step': 'phone'})


def logout(request):
    request.session.flush()
    return redirect('landing')


# ─── Setup profil (onboarding nouveaux agriculteurs) ─────────────────────────

def setup(request):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')

    if request.method == 'POST':
        name    = request.POST.get('name', '').strip()
        region  = request.POST.get('region', '').strip()
        surface = request.POST.get('surface', '1').strip()
        crops   = request.POST.getlist('crops')

        if not name or not region:
            messages.error(request, 'Nom et région sont obligatoires.')
        else:
            try:
                surface_f = float(surface) if surface else 1.0
            except ValueError:
                surface_f = 1.0

            farmer.name    = name
            farmer.region  = region
            farmer.surface = surface_f
            farmer.crops   = crops
            farmer.save(update_fields=['name', 'region', 'surface', 'crops'])
            return redirect('dashboard')

    return render(request, 'setup.html', {
        'regions': list(REGION_COORDS.keys()),
        'crops_catalog': CROPS_CATALOG,
        'farmer': farmer,
    })


# ─── Dashboard ────────────────────────────────────────────────────────────────

def dashboard(request):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')
    if not farmer.name:
        return redirect('setup')

    active_credit = CreditApplication.objects.filter(farmer=farmer, status='active').first()
    insurance     = InsurancePolicy.objects.filter(farmer=farmer, is_active=True).first()
    listings      = Listing.objects.filter(farmer=farmer, is_active=True)[:3]

    farmer_offers  = Offer.objects.filter(listing__farmer=farmer)
    pending_offers = farmer_offers.filter(status='pending').select_related('listing')
    pending_count  = pending_offers.count()
    recent_offers  = pending_offers[:5]

    accepted_total = farmer_offers.filter(status='accepted').aggregate(s=Sum('total'))['s'] or 0
    accepted_count = farmer_offers.filter(status='accepted').count()
    total_rev   = farmer.total_revenue + accepted_total
    total_tx    = farmer.total_transactions + accepted_count
    total_saved = farmer.saved_vs_intermediaries

    return render(request, 'dashboard.html', {
        'farmer':         farmer,
        'active_credit':  active_credit,
        'insurance':      insurance,
        'listings':       listings,
        'market_prices':  get_market_prices()[:5],
        'revenue_bars':   get_revenue_bars(farmer),
        'pending_count':  pending_count,
        'recent_offers':  recent_offers,
        'total_rev':      total_rev,
        'total_tx':       total_tx,
        'total_saved':    total_saved,
        'platform_stats': get_platform_stats(),
    })


# ─── Marketplace ─────────────────────────────────────────────────────────────

def marketplace(request):
    q           = request.GET.get('q', '')
    crop_filter = request.GET.get('crop', '')
    listings    = Listing.objects.filter(is_active=True).select_related('farmer')
    if q:
        listings = listings.filter(crop__icontains=q)
    if crop_filter:
        listings = listings.filter(crop__iexact=crop_filter)
    crops = Listing.objects.filter(is_active=True).values_list('crop', flat=True).distinct()
    return render(request, 'marketplace/list.html', {
        'listings':      listings,
        'crops':         crops,
        'q':             q,
        'crop_filter':   crop_filter,
        'market_prices': get_market_prices(),
    })


def listing_detail(request, pk):
    listing = get_object_or_404(Listing, pk=pk, is_active=True)
    listing.views += 1
    listing.save(update_fields=['views'])
    prices = get_market_prices()
    market = next((p for p in prices if p['crop'].lower() in listing.crop.lower()), None)

    if request.method == 'POST':
        buyer_name   = request.POST.get('buyer_name', '').strip()
        buyer_phone  = request.POST.get('buyer_phone', '').strip()
        buyer_region = request.POST.get('buyer_region', 'Dakar').strip()
        quantity     = int(request.POST.get('quantity', 100))
        offer_price  = int(request.POST.get('offer_price', listing.price_per_kg))
        total        = quantity * offer_price

        if not buyer_name:
            messages.error(request, 'Votre nom est obligatoire.')
            return render(request, 'marketplace/detail.html', {
                'listing': listing, 'market': market, 'offer_sent': False,
                'regions': list(REGION_COORDS.keys()),
            })

        Offer.objects.create(
            listing      = listing,
            buyer_name   = buyer_name,
            buyer_phone  = buyer_phone,
            buyer_region = buyer_region,
            quantity     = quantity,
            price_per_kg = offer_price,
            total        = total,
        )
        return render(request, 'marketplace/detail.html', {
            'listing': listing, 'market': market,
            'offer_sent': True, 'quantity': quantity,
            'offer_price': offer_price, 'total': total,
        })

    return render(request, 'marketplace/detail.html', {
        'listing': listing, 'market': market, 'offer_sent': False,
        'regions': list(REGION_COORDS.keys()),
    })


def listing_new(request):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')
    if not farmer.name:
        return redirect('setup')

    if request.method == 'POST' and request.POST.get('step') == 'submit':
        crop = request.POST.get('crop', '').strip()
        emoji = CROPS_EMOJI.get(crop, '🌾')
        market_ref = CROPS_BASE.get(crop, 200)
        Listing.objects.create(
            farmer       = farmer,
            crop         = crop,
            emoji        = emoji,
            quantity     = int(request.POST.get('quantity', 500)),
            quality      = request.POST.get('quality', 'Grade A'),
            price_per_kg = int(request.POST.get('price_per_kg', market_ref)),
            market_price = market_ref,
            description  = request.POST.get('description', ''),
            region       = farmer.region,
            available    = request.POST.get('available', date.today().isoformat()),
        )
        return redirect('marketplace')

    return render(request, 'marketplace/new.html', {
        'market_prices':  get_market_prices(),
        'crops_catalog':  CROPS_CATALOG,
        'farmer':         farmer,
        'today':          date.today().isoformat(),
    })


def listing_delete(request, pk):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')
    listing = get_object_or_404(Listing, pk=pk, farmer=farmer)
    listing.is_active = False
    listing.save(update_fields=['is_active'])
    return redirect('profil')


# ─── Offres (accept / reject) ─────────────────────────────────────────────────

@require_POST
def offer_action(request, offer_id):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')
    offer  = get_object_or_404(Offer, id=offer_id, listing__farmer=farmer)
    action = request.POST.get('action')

    if action == 'accept' and offer.status == 'pending':
        offer.status = 'accepted'
        offer.save(update_fields=['status'])
        # Mark other pending offers for same listing as rejected
        Offer.objects.filter(listing=offer.listing, status='pending').exclude(id=offer.id).update(status='rejected')
        # Update farmer's base stats
        farmer.total_revenue      += offer.total
        farmer.total_transactions += 1
        saved = round(offer.total * 0.15)
        farmer.saved_vs_intermediaries += saved
        farmer.save(update_fields=['total_revenue', 'total_transactions', 'saved_vs_intermediaries'])

    elif action == 'reject' and offer.status == 'pending':
        offer.status = 'rejected'
        offer.save(update_fields=['status'])

    return redirect('dashboard')


# ─── Crédit ──────────────────────────────────────────────────────────────────

def credit_index(request):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')
    if not farmer.name:
        return redirect('setup')

    credits = CreditApplication.objects.filter(farmer=farmer).order_by('-created_at')

    # Score criteria based on real farmer data
    tx_count = farmer.total_transactions
    has_repaid = credits.filter(status='repaid').exists()
    score_criteria = [
        {'label': 'Historique transactions',  'weight': 30,
         'score': min(100, tx_count * 10) if tx_count else 20},
        {'label': 'Remboursement crédits',    'weight': 25,
         'score': 100 if has_repaid else (50 if credits.filter(status='active').exists() else 30)},
        {'label': 'Surface cultivée',         'weight': 20,
         'score': min(100, round(farmer.surface * 20))},
        {'label': 'Ancienneté plateforme',    'weight': 15,
         'score': min(100, (date.today() - farmer.created_at.date()).days // 3)},
        {'label': 'Diversification cultures', 'weight': 10,
         'score': min(100, len(farmer.crops) * 25)},
    ]
    return render(request, 'credit/index.html', {
        'farmer':         farmer,
        'credits':        credits,
        'imf_partners':   IMF_PARTNERS,
        'score_criteria': score_criteria,
    })


def credit_apply(request):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')
    if not farmer.name:
        return redirect('setup')

    if request.method == 'POST' and request.POST.get('step') == 'submit':
        imf_id = request.POST.get('imf', 'boa')
        imf    = next((i for i in IMF_PARTNERS if i['id'] == imf_id), IMF_PARTNERS[0])
        CreditApplication.objects.create(
            farmer        = farmer,
            amount        = int(request.POST.get('amount', 100000)),
            duration      = int(request.POST.get('duration', 6)),
            purpose       = request.POST.get('purpose', 'Semences'),
            purpose_emoji = request.POST.get('purpose_emoji', '🌱'),
            imf_name      = imf['name'],
            rate          = imf['rate'],
            status        = 'pending',
        )
        return render(request, 'credit/apply.html', {'submitted': True, 'imf_partners': IMF_PARTNERS})
    return render(request, 'credit/apply.html', {
        'imf_partners': IMF_PARTNERS,
        'submitted':    False,
    })


# ─── Assurance ───────────────────────────────────────────────────────────────

def insurance_index(request):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')
    if not farmer.name:
        return redirect('setup')

    policy  = InsurancePolicy.objects.filter(farmer=farmer, is_active=True).first()
    weather = get_weather(farmer.region)
    if weather and policy:
        policy.rainfall_30d = weather['rainfall_30d']
        policy.risk_index   = weather['risk_index']
        policy.save(update_fields=['rainfall_30d', 'risk_index'])
    return render(request, 'insurance/index.html', {
        'farmer': farmer, 'policy': policy, 'weather': weather,
    })


def insurance_new(request):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')
    if not farmer.name:
        return redirect('setup')

    if request.method == 'POST' and request.POST.get('step') == 'submit':
        crop    = request.POST.get('crop', 'Arachide')
        surface = float(request.POST.get('surface', farmer.surface))
        premium = round(surface * 12000)
        InsurancePolicy.objects.create(
            farmer     = farmer,
            crop       = crop,
            crop_emoji = CROPS_EMOJI.get(crop, '🌾'),
            surface    = surface,
            season     = request.POST.get('season', 'Hivernage 2026'),
            premium    = premium,
            coverage   = premium * 8,
        )
        return render(request, 'insurance/new.html', {'submitted': True, 'farmer': farmer})
    return render(request, 'insurance/new.html', {
        'submitted':     False,
        'farmer':        farmer,
        'crops_catalog': CROPS_CATALOG,
    })


# ─── Conseiller IA ───────────────────────────────────────────────────────────

def conseiller(request):
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    history     = list(ChatMessage.objects.filter(session_key=session_key).values('role', 'content'))
    suggestions = [
        "Comment traiter la rosette de l'arachide ?",
        "Quand planter le mil à Kaolack ?",
        "Quel engrais pour 1 ha de maïs ?",
        "Techniques d'irrigation économique",
        "Prix du marché pour la tomate",
        "Maladies courantes du maraîchage",
    ]
    return render(request, 'conseiller/chat.html', {
        'history_json': json.dumps(history),
        'suggestions':  suggestions,
    })


@csrf_exempt
def conseiller_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    data        = json.loads(request.body)
    message     = data.get('message', '')
    history     = data.get('history', [])
    session_key = request.session.session_key or 'anon'

    if not settings.GROQ_API_KEY:
        return JsonResponse(
            {'error': 'Clé API Groq non configurée. Ajoutez GROQ_API_KEY dans les variables Railway.'},
            status=500,
        )

    try:
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {settings.GROQ_API_KEY}', 'Content-Type': 'application/json'},
            json={
                'model':       'llama-3.3-70b-versatile',
                'messages':    [{'role': 'system', 'content': GROQ_SYSTEM_PROMPT},
                                *history,
                                {'role': 'user', 'content': message}],
                'max_tokens':  1024,
                'temperature': 0.7,
            },
            timeout=30,
        )
        result  = response.json()
        content = result['choices'][0]['message']['content']
        ChatMessage.objects.create(session_key=session_key, role='user',      content=message)
        ChatMessage.objects.create(session_key=session_key, role='assistant', content=content)
        return JsonResponse({'content': content})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Profil ──────────────────────────────────────────────────────────────────

def profil(request):
    farmer = get_current_farmer(request)
    if not farmer:
        return redirect('auth')
    if not farmer.name:
        return redirect('setup')

    # Handle profile edit
    if request.method == 'POST' and request.POST.get('step') == 'edit':
        name    = request.POST.get('name', '').strip()
        region  = request.POST.get('region', '').strip()
        surface = request.POST.get('surface', '').strip()
        crops   = request.POST.getlist('crops')
        if name:
            farmer.name = name
        if region:
            farmer.region = region
        if surface:
            try:
                farmer.surface = float(surface)
            except ValueError:
                pass
        if crops:
            farmer.crops = crops
        farmer.save()
        messages.success(request, 'Profil mis à jour.')
        return redirect('profil')

    credits      = CreditApplication.objects.filter(farmer=farmer).order_by('-created_at')
    listings     = Listing.objects.filter(farmer=farmer, is_active=True)
    revenue_bars = get_revenue_bars(farmer)

    accepted_total = (
        Offer.objects.filter(listing__farmer=farmer, status='accepted')
        .aggregate(s=Sum('total'))['s'] or 0
    )
    total_rev = farmer.total_revenue + accepted_total

    return render(request, 'profil/index.html', {
        'farmer':           farmer,
        'credits':          credits,
        'listings':         listings,
        'revenue_bars':     revenue_bars,
        'regions':          list(REGION_COORDS.keys()),
        'crops_catalog':    CROPS_CATALOG,
        'total_rev':        total_rev,
    })
