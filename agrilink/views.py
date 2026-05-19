import json
import random
import hashlib
import requests
from datetime import date, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib import messages

from .models import Farmer, Listing, CreditApplication, InsurancePolicy, ChatMessage

DEMO_FARMER_PHONE = '+221 77 000 00 01'

# Coordinates for major Senegal regions
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

BASE_PRICES = [
    {'crop': 'Arachide', 'base': 385, 'emoji': '🥜'},
    {'crop': 'Mil',      'base': 195, 'emoji': '🌾'},
    {'crop': 'Maïs',     'base': 165, 'emoji': '🌽'},
    {'crop': 'Tomate',   'base': 280, 'emoji': '🍅'},
    {'crop': 'Oignon',   'base': 320, 'emoji': '🧅'},
    {'crop': 'Mangue',   'base': 150, 'emoji': '🥭'},
]

IMF_PARTNERS = [
    {'id': 'boa',     'name': 'Bank of Africa',  'logo': '🏦', 'rate': 7.5, 'max_amount': 500000, 'coverage': 'Sénégal · UEMOA'},
    {'id': 'cncas',   'name': 'CNCAS',           'logo': '🌱', 'rate': 6.0, 'max_amount': 300000, 'coverage': 'Agriculture uniquement'},
    {'id': 'pamecas', 'name': 'PAMECAS',         'logo': '🤝', 'rate': 8.0, 'max_amount': 200000, 'coverage': 'Petits producteurs'},
    {'id': 'axa',     'name': 'AXA Microfinance','logo': '💼', 'rate': 9.0, 'max_amount': 150000, 'coverage': 'Crédit rapide 24h'},
]

REVENUE_DATA = [
    {'month': 'Jan', 'revenue': 145000}, {'month': 'Fév', 'revenue': 189000},
    {'month': 'Mar', 'revenue': 234000}, {'month': 'Avr', 'revenue': 178000},
    {'month': 'Mai', 'revenue': 312000}, {'month': 'Jun', 'revenue': 267000},
    {'month': 'Jul', 'revenue': 198000}, {'month': 'Aoû', 'revenue': 445000},
    {'month': 'Sep', 'revenue': 389000}, {'month': 'Oct', 'revenue': 523000},
    {'month': 'Nov', 'revenue': 456000}, {'month': 'Déc', 'revenue': 612000},
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


# ─── Prix dynamiques (variation journalière déterministe) ──────────────────

def get_market_prices():
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = []
    for item in BASE_PRICES:
        def day_price(d):
            h = int(hashlib.md5(f"{item['crop']}{d}".encode()).hexdigest()[:8], 16)
            variation = ((h % 101) - 50) / 1000  # ±5%
            return round(item['base'] * (1 + variation))
        price   = day_price(today)
        price_y = day_price(yesterday)
        change  = round(((price - price_y) / price_y) * 100, 1)
        result.append({'crop': item['crop'], 'price': price, 'change': change, 'emoji': item['emoji']})
    return result


# ─── SMS OTP via Twilio ───────────────────────────────────────────────────

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


# ─── Météo via OpenWeatherMap ──────────────────────────────────────────────

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
        data = r.json()
        rain_1h    = data.get('rain', {}).get('1h', 0)
        humidity   = data.get('main', {}).get('humidity', 50)
        temp       = data.get('main', {}).get('temp', 30)
        description = data.get('weather', [{}])[0].get('description', '').capitalize()

        # Estimate 30-day rainfall from current conditions
        rainfall_30d = round(rain_1h * 24 * 30, 1) if rain_1h else round(humidity * 0.3, 1)

        # Risk index: high humidity + high temp = higher risk
        risk_index = min(100, round((humidity * 0.5) + (max(0, temp - 25) * 2)))

        result = {
            'rainfall_30d': rainfall_30d,
            'risk_index': risk_index,
            'humidity': humidity,
            'temp': temp,
            'description': description,
        }
        _weather_cache[cache_key] = result
        return result
    except Exception:
        return None


# ─── Utilitaires ──────────────────────────────────────────────────────────

def format_cfa(amount):
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M FCFA"
    if amount >= 1_000:
        return f"{amount:,.0f}".replace(',', ' ') + " FCFA"
    return f"{amount} FCFA"


# ─── Landing ──────────────────────────────────────────────────────────────

def landing(request):
    return render(request, 'landing.html')


# ─── Auth ─────────────────────────────────────────────────────────────────

def auth(request):
    if request.method == 'POST':
        step = request.POST.get('step')

        if step == 'otp':
            otp_input    = request.POST.get('otp', '').strip()
            expected_otp = request.session.get('otp_code', '')
            otp_phone    = request.session.get('otp_phone', DEMO_FARMER_PHONE)

            if otp_input == expected_otp:
                try:
                    farmer = Farmer.objects.get(phone=otp_phone)
                except Farmer.DoesNotExist:
                    farmer = Farmer.objects.get(phone=DEMO_FARMER_PHONE)
                request.session['farmer_id'] = farmer.id
                return redirect('dashboard')
            messages.error(request, 'Code incorrect. Réessayez.')

        elif step == 'phone':
            phone = request.POST.get('phone', '').strip()
            otp   = str(random.randint(100000, 999999))
            request.session['otp_code']  = otp
            request.session['otp_phone'] = phone

            sms_sent = send_otp_sms(phone, otp)
            return render(request, 'auth.html', {
                'step':     'otp',
                'phone':    phone,
                'demo_otp': None if sms_sent else otp,
            })

    return render(request, 'auth.html', {'step': 'phone'})


def logout(request):
    request.session.flush()
    return redirect('landing')


# ─── Dashboard ────────────────────────────────────────────────────────────

def dashboard(request):
    farmer    = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    credits   = CreditApplication.objects.filter(farmer=farmer, status='active').first()
    insurance = InsurancePolicy.objects.filter(farmer=farmer, is_active=True).first()
    listings  = Listing.objects.filter(farmer=farmer, is_active=True)[:3]
    max_rev   = max(d['revenue'] for d in REVENUE_DATA)

    revenue_bars = [
        {'month': d['month'], 'pct': round((d['revenue'] / max_rev) * 100), 'revenue': d['revenue']}
        for d in REVENUE_DATA
    ]

    return render(request, 'dashboard.html', {
        'farmer':        farmer,
        'active_credit': credits,
        'insurance':     insurance,
        'listings':      listings,
        'market_prices': get_market_prices()[:5],
        'revenue_bars':  revenue_bars,
    })


# ─── Marketplace ──────────────────────────────────────────────────────────

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
    listing = get_object_or_404(Listing, pk=pk)
    listing.views += 1
    listing.save(update_fields=['views'])
    prices = get_market_prices()
    market = next((p for p in prices if p['crop'].lower() in listing.crop.lower()), None)

    if request.method == 'POST':
        quantity    = int(request.POST.get('quantity', 100))
        offer_price = int(request.POST.get('offer_price', listing.price_per_kg))
        return render(request, 'marketplace/detail.html', {
            'listing':    listing,
            'market':     market,
            'offer_sent': True,
            'quantity':   quantity,
            'offer_price':offer_price,
            'total':      quantity * offer_price,
        })

    return render(request, 'marketplace/detail.html', {
        'listing':    listing,
        'market':     market,
        'offer_sent': False,
    })


def listing_new(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    if request.method == 'POST' and request.POST.get('step') == 'submit':
        Listing.objects.create(
            farmer       = farmer,
            crop         = request.POST.get('crop', ''),
            emoji        = request.POST.get('emoji', '🌾'),
            quantity     = int(request.POST.get('quantity', 500)),
            quality      = request.POST.get('quality', 'Grade A'),
            price_per_kg = int(request.POST.get('price_per_kg', 200)),
            market_price = int(request.POST.get('market_price', 250)),
            description  = request.POST.get('description', ''),
            region       = request.POST.get('region', 'Kaolack'),
            available    = request.POST.get('available', '2026-06-01'),
        )
        return redirect('marketplace')
    return render(request, 'marketplace/new.html', {'market_prices': get_market_prices()})


# ─── Crédit ───────────────────────────────────────────────────────────────

def credit_index(request):
    farmer  = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    credits = CreditApplication.objects.filter(farmer=farmer).order_by('-created_at')
    score_criteria = [
        {'label': 'Historique transactions',  'weight': 30, 'score': 78,  'icon': '📊'},
        {'label': 'Remboursement crédits',    'weight': 25, 'score': 100, 'icon': '✅'},
        {'label': 'Surface cultivée',         'weight': 20, 'score': 60,  'icon': '🌾'},
        {'label': 'Ancienneté plateforme',    'weight': 15, 'score': 80,  'icon': '📅'},
        {'label': 'Diversification cultures', 'weight': 10, 'score': 70,  'icon': '🌿'},
    ]
    return render(request, 'credit/index.html', {
        'farmer':         farmer,
        'credits':        credits,
        'imf_partners':   IMF_PARTNERS,
        'score_criteria': score_criteria,
    })


def credit_apply(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
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
            status        = 'active',
        )
        return render(request, 'credit/apply.html', {'submitted': True})
    return render(request, 'credit/apply.html', {
        'imf_partners': IMF_PARTNERS,
        'submitted':    False,
    })


# ─── Assurance ────────────────────────────────────────────────────────────

def insurance_index(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    policy = InsurancePolicy.objects.filter(farmer=farmer, is_active=True).first()

    weather = get_weather(farmer.region)
    if weather and policy:
        policy.rainfall_30d = weather['rainfall_30d']
        policy.risk_index   = weather['risk_index']
        policy.save(update_fields=['rainfall_30d', 'risk_index'])

    return render(request, 'insurance/index.html', {
        'farmer':  farmer,
        'policy':  policy,
        'weather': weather,
    })


def insurance_new(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    if request.method == 'POST' and request.POST.get('step') == 'submit':
        surface = float(request.POST.get('surface', 1))
        premium = round(surface * 12000)
        InsurancePolicy.objects.create(
            farmer     = farmer,
            crop       = request.POST.get('crop', 'Arachide'),
            crop_emoji = request.POST.get('crop_emoji', '🥜'),
            surface    = surface,
            season     = request.POST.get('season', 'Hivernage 2026'),
            premium    = premium,
            coverage   = premium * 8,
        )
        return render(request, 'insurance/new.html', {'submitted': True})
    return render(request, 'insurance/new.html', {'submitted': False})


# ─── Conseiller IA ────────────────────────────────────────────────────────

def conseiller(request):
    session_key = request.session.session_key or 'anon'
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

    data       = json.loads(request.body)
    message    = data.get('message', '')
    history    = data.get('history', [])
    session_key= request.session.session_key or 'anon'

    if not settings.GROQ_API_KEY:
        return JsonResponse({'error': 'Clé API Groq non configurée'}, status=500)

    try:
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={'Authorization': f'Bearer {settings.GROQ_API_KEY}', 'Content-Type': 'application/json'},
            json={
                'model':       'llama-3.3-70b-versatile',
                'messages':    [{'role': 'system', 'content': GROQ_SYSTEM_PROMPT}, *history, {'role': 'user', 'content': message}],
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


# ─── Profil ───────────────────────────────────────────────────────────────

def profil(request):
    farmer   = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    credits  = CreditApplication.objects.filter(farmer=farmer).order_by('-created_at')
    listings = Listing.objects.filter(farmer=farmer, is_active=True)
    max_rev  = max(d['revenue'] for d in REVENUE_DATA)
    revenue_bars = [
        {'month': d['month'], 'pct': round((d['revenue'] / max_rev) * 100)}
        for d in REVENUE_DATA
    ]
    return render(request, 'profil/index.html', {
        'farmer':        farmer,
        'credits':       credits,
        'listings':      listings,
        'revenue_bars':  revenue_bars,
    })
