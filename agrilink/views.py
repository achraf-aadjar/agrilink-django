import json
import requests
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.contrib import messages

from .models import Farmer, Listing, CreditApplication, InsurancePolicy, ChatMessage

DEMO_FARMER_PHONE = '+221 77 000 00 01'

MARKET_PRICES = [
    {'crop': 'Arachide', 'price': 385, 'change': 2.3, 'emoji': '🥜'},
    {'crop': 'Mil', 'price': 195, 'change': -1.2, 'emoji': '🌾'},
    {'crop': 'Maïs', 'price': 165, 'change': 4.1, 'emoji': '🌽'},
    {'crop': 'Tomate', 'price': 280, 'change': -3.5, 'emoji': '🍅'},
    {'crop': 'Oignon', 'price': 320, 'change': 1.8, 'emoji': '🧅'},
    {'crop': 'Mangue', 'price': 150, 'change': 6.2, 'emoji': '🥭'},
]

IMF_PARTNERS = [
    {'id': 'boa', 'name': 'Bank of Africa', 'logo': '🏦', 'rate': 7.5, 'max_amount': 500000, 'coverage': 'Sénégal · UEMOA'},
    {'id': 'cncas', 'name': 'CNCAS', 'logo': '🌱', 'rate': 6.0, 'max_amount': 300000, 'coverage': 'Agriculture uniquement'},
    {'id': 'pamecas', 'name': 'PAMECAS', 'logo': '🤝', 'rate': 8.0, 'max_amount': 200000, 'coverage': 'Petits producteurs'},
    {'id': 'axa', 'name': 'AXA Microfinance', 'logo': '💼', 'rate': 9.0, 'max_amount': 150000, 'coverage': 'Crédit rapide 24h'},
]

REVENUE_DATA = [
    {'month': 'Jan', 'revenue': 145000},
    {'month': 'Fév', 'revenue': 189000},
    {'month': 'Mar', 'revenue': 234000},
    {'month': 'Avr', 'revenue': 178000},
    {'month': 'Mai', 'revenue': 312000},
    {'month': 'Jun', 'revenue': 267000},
    {'month': 'Jul', 'revenue': 198000},
    {'month': 'Aoû', 'revenue': 445000},
    {'month': 'Sep', 'revenue': 389000},
    {'month': 'Oct', 'revenue': 523000},
    {'month': 'Nov', 'revenue': 456000},
    {'month': 'Déc', 'revenue': 612000},
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


def format_cfa(amount):
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M FCFA"
    if amount >= 1_000:
        return f"{amount:,.0f}".replace(',', ' ') + " FCFA"
    return f"{amount} FCFA"


# ─── Landing ───────────────────────────────────────────────────────────────

def landing(request):
    return render(request, 'landing.html')


# ─── Auth ──────────────────────────────────────────────────────────────────

def auth(request):
    if request.method == 'POST':
        step = request.POST.get('step')
        if step == 'otp':
            otp = request.POST.get('otp', '')
            if otp == '123456':
                request.session['farmer_id'] = Farmer.objects.get(phone=DEMO_FARMER_PHONE).id
                return redirect('dashboard')
            messages.error(request, 'Code incorrect. Démo : 123456')
        elif step == 'phone':
            return render(request, 'auth.html', {'step': 'otp', 'phone': request.POST.get('phone')})
    return render(request, 'auth.html', {'step': 'phone'})


def logout(request):
    request.session.flush()
    return redirect('landing')


# ─── Dashboard ─────────────────────────────────────────────────────────────

def dashboard(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    credits = CreditApplication.objects.filter(farmer=farmer, status='active').first()
    insurance = InsurancePolicy.objects.filter(farmer=farmer, is_active=True).first()
    listings = Listing.objects.filter(farmer=farmer, is_active=True)[:3]
    max_rev = max(d['revenue'] for d in REVENUE_DATA)

    revenue_bars = [
        {'month': d['month'], 'pct': round((d['revenue'] / max_rev) * 100), 'revenue': d['revenue']}
        for d in REVENUE_DATA
    ]

    return render(request, 'dashboard.html', {
        'farmer': farmer,
        'active_credit': credits,
        'insurance': insurance,
        'listings': listings,
        'market_prices': MARKET_PRICES[:5],
        'revenue_bars': revenue_bars,
        'format_cfa': format_cfa,
    })


# ─── Marketplace ───────────────────────────────────────────────────────────

def marketplace(request):
    q = request.GET.get('q', '')
    crop_filter = request.GET.get('crop', '')
    listings = Listing.objects.filter(is_active=True).select_related('farmer')
    if q:
        listings = listings.filter(crop__icontains=q)
    if crop_filter:
        listings = listings.filter(crop__iexact=crop_filter)
    crops = Listing.objects.filter(is_active=True).values_list('crop', flat=True).distinct()
    return render(request, 'marketplace/list.html', {
        'listings': listings,
        'crops': crops,
        'q': q,
        'crop_filter': crop_filter,
        'market_prices': MARKET_PRICES,
    })


def listing_detail(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    listing.views += 1
    listing.save(update_fields=['views'])
    market = next((p for p in MARKET_PRICES if p['crop'].lower() in listing.crop.lower()), None)

    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 100))
        offer_price = int(request.POST.get('offer_price', listing.price_per_kg))
        return render(request, 'marketplace/detail.html', {
            'listing': listing,
            'market': market,
            'offer_sent': True,
            'quantity': quantity,
            'offer_price': offer_price,
            'total': quantity * offer_price,
        })

    return render(request, 'marketplace/detail.html', {
        'listing': listing,
        'market': market,
        'offer_sent': False,
    })


def listing_new(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    if request.method == 'POST' and request.POST.get('step') == 'submit':
        Listing.objects.create(
            farmer=farmer,
            crop=request.POST.get('crop', ''),
            emoji=request.POST.get('emoji', '🌾'),
            quantity=int(request.POST.get('quantity', 500)),
            quality=request.POST.get('quality', 'Grade A'),
            price_per_kg=int(request.POST.get('price_per_kg', 200)),
            market_price=int(request.POST.get('market_price', 250)),
            description=request.POST.get('description', ''),
            region=request.POST.get('region', 'Kaolack'),
            available=request.POST.get('available', '2026-06-01'),
        )
        return redirect('marketplace')
    return render(request, 'marketplace/new.html', {'market_prices': MARKET_PRICES})


# ─── Credit ────────────────────────────────────────────────────────────────

def credit_index(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    credits = CreditApplication.objects.filter(farmer=farmer).order_by('-created_at')
    score_criteria = [
        {'label': 'Historique transactions', 'weight': 30, 'score': 78, 'icon': '📊'},
        {'label': 'Remboursement crédits', 'weight': 25, 'score': 100, 'icon': '✅'},
        {'label': 'Surface cultivée', 'weight': 20, 'score': 60, 'icon': '🌾'},
        {'label': 'Ancienneté plateforme', 'weight': 15, 'score': 80, 'icon': '📅'},
        {'label': 'Diversification cultures', 'weight': 10, 'score': 70, 'icon': '🌿'},
    ]
    return render(request, 'credit/index.html', {
        'farmer': farmer,
        'credits': credits,
        'imf_partners': IMF_PARTNERS,
        'score_criteria': score_criteria,
    })


def credit_apply(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    if request.method == 'POST' and request.POST.get('step') == 'submit':
        imf_id = request.POST.get('imf', 'boa')
        imf = next((i for i in IMF_PARTNERS if i['id'] == imf_id), IMF_PARTNERS[0])
        CreditApplication.objects.create(
            farmer=farmer,
            amount=int(request.POST.get('amount', 100000)),
            duration=int(request.POST.get('duration', 6)),
            purpose=request.POST.get('purpose', 'Semences'),
            purpose_emoji=request.POST.get('purpose_emoji', '🌱'),
            imf_name=imf['name'],
            rate=imf['rate'],
            status='active',
        )
        return render(request, 'credit/apply.html', {'submitted': True})
    return render(request, 'credit/apply.html', {
        'imf_partners': IMF_PARTNERS,
        'submitted': False,
    })


# ─── Insurance ─────────────────────────────────────────────────────────────

def insurance_index(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    policy = InsurancePolicy.objects.filter(farmer=farmer, is_active=True).first()
    return render(request, 'insurance/index.html', {
        'farmer': farmer,
        'policy': policy,
    })


def insurance_new(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    if request.method == 'POST' and request.POST.get('step') == 'submit':
        surface = float(request.POST.get('surface', 1))
        premium = round(surface * 12000)
        InsurancePolicy.objects.create(
            farmer=farmer,
            crop=request.POST.get('crop', 'Arachide'),
            crop_emoji=request.POST.get('crop_emoji', '🥜'),
            surface=surface,
            season=request.POST.get('season', 'hivernage'),
            premium=premium,
            coverage=premium * 8,
        )
        return render(request, 'insurance/new.html', {'submitted': True})
    return render(request, 'insurance/new.html', {'submitted': False})


# ─── Conseiller IA ─────────────────────────────────────────────────────────

def conseiller(request):
    session_key = request.session.session_key or 'anon'
    history = list(ChatMessage.objects.filter(session_key=session_key).values('role', 'content'))
    return render(request, 'conseiller/chat.html', {'history_json': json.dumps(history)})


@csrf_exempt
def conseiller_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    data = json.loads(request.body)
    message = data.get('message', '')
    history = data.get('history', [])
    session_key = request.session.session_key or 'anon'

    if not settings.GROQ_API_KEY:
        return JsonResponse({'error': 'Clé API Groq non configurée'}, status=500)

    try:
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {settings.GROQ_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'llama-3.3-70b-versatile',
                'messages': [
                    {'role': 'system', 'content': GROQ_SYSTEM_PROMPT},
                    *history,
                    {'role': 'user', 'content': message},
                ],
                'max_tokens': 1024,
                'temperature': 0.7,
            },
            timeout=30,
        )
        result = response.json()
        content = result['choices'][0]['message']['content']

        ChatMessage.objects.create(session_key=session_key, role='user', content=message)
        ChatMessage.objects.create(session_key=session_key, role='assistant', content=content)

        return JsonResponse({'content': content})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── Profil ────────────────────────────────────────────────────────────────

def profil(request):
    farmer = get_object_or_404(Farmer, phone=DEMO_FARMER_PHONE)
    credits = CreditApplication.objects.filter(farmer=farmer).order_by('-created_at')
    listings = Listing.objects.filter(farmer=farmer, is_active=True)
    max_rev = max(d['revenue'] for d in REVENUE_DATA)
    revenue_bars = [
        {'month': d['month'], 'pct': round((d['revenue'] / max_rev) * 100)}
        for d in REVENUE_DATA
    ]
    return render(request, 'profil/index.html', {
        'farmer': farmer,
        'credits': credits,
        'listings': listings,
        'revenue_bars': revenue_bars,
    })
