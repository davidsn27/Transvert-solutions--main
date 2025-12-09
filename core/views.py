# -------------------------------
# IMPORTS GENERALES
# -------------------------------
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.conf import settings 

import uuid
import json
import tempfile
import os
import qrcode

try:
    from google import genai
except ImportError:
    genai = None

# Importamos modelos y formularios
from .models import Envio, TrazaEnvio, SoporteTicket, SoporteRespuesta, Zona, Tarifa
from .forms import CustomUserCreationForm, CustomAuthenticationForm

# ReportLab para PDF
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A6
except ImportError:
    canvas = None


# -------------------------------
# LOGIN / LOGOUT / REGISTRO
# -------------------------------
def register(request):
    form = CustomUserCreationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Registro exitoso.')
        return redirect('login')
    return render(request, 'register.html', {'form': form})


def login_view(request):
    form = CustomAuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(
            username=form.cleaned_data.get('username'),
            password=form.cleaned_data.get('password')
        )
        if user:
            login(request, user)
            if user.is_superuser:
                return redirect('superadmin_panel')
            elif user.is_staff:
                return redirect('staff_panel')
            else:
                return redirect('client_dashboard')
        messages.error(request, "Usuario o contraseña incorrectos")
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('index')


# -------------------------------
# PÁGINAS PÚBLICAS
# -------------------------------
def home(request):
    return render(request, 'home.html')


def index(request):
    return render(request, 'index.html')


def contact(request):
    return render(request, 'contact.html')


# -------------------------------
# PANELES
# -------------------------------
@login_required(login_url='login')
def staff_panel(request):
    envios = Envio.objects.all().order_by('-fecha_creado')
    tickets = SoporteTicket.objects.all().order_by('-fecha')

    # Filtrar envíos
    estado_envio = request.GET.get('estado_envio')
    if estado_envio:
        envios = envios.filter(estado=estado_envio)

    # Filtrar tickets
    estado_ticket = request.GET.get('estado_ticket')
    if estado_ticket:
        tickets = tickets.filter(estado=estado_ticket)

    return render(request, 'staff_panel.html', {
        'envios': envios,
        'tickets': tickets
    })


@login_required(login_url='login')
def superadmin_panel(request):
    usuarios = User.objects.all()
    envios = Envio.objects.all().order_by('-fecha_creado')
    tickets = SoporteTicket.objects.all().order_by('-fecha')

    # Filtrar envíos
    estado_envio = request.GET.get('estado_envio')
    if estado_envio:
        envios = envios.filter(estado=estado_envio)

    # Filtrar tickets
    estado_ticket = request.GET.get('estado_ticket')
    if estado_ticket:
        tickets = tickets.filter(estado=estado_ticket)

    return render(request, 'superadmin_panel.html', {
        'usuarios': usuarios,
        'envios': envios,
        'tickets': tickets
    })


@login_required(login_url='login')
def client_dashboard(request):
    envios_del_usuario = Envio.objects.filter(usuario=request.user).order_by('-fecha_creado')
    tickets_del_usuario = SoporteTicket.objects.filter(usuario=request.user).order_by('-fecha')

    return render(request, 'client_dashboard.html', {
        'envios': envios_del_usuario,
        'tickets': tickets_del_usuario
    })


# -------------------------------
# COTIZACIÓN DE ENVÍO
# -------------------------------
def calcular_peso_volumetrico(largo, ancho, alto, factor_divisor=5000):
    try:
        largo, ancho, alto, factor_divisor = float(largo), float(ancho), float(alto), int(factor_divisor)
        if largo <= 0 or ancho <= 0 or alto <= 0:
            return 0.0
        return (largo * ancho * alto) / factor_divisor
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0


@csrf_exempt
def cotizar_envio(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            origen_nombre = data.get('origen')
            destino_nombre = data.get('destino')
            peso_real = float(data.get('peso', 0))
            largo = float(data.get('largo', 0))
            ancho = float(data.get('ancho', 0))
            alto = float(data.get('alto', 0))

            if not origen_nombre or not destino_nombre:
                return JsonResponse({'success': False, 'error': 'Origen y Destino obligatorios.'}, status=400)

            zona_origen = Zona.objects.get(nombre__iexact=origen_nombre)
            zona_destino = Zona.objects.get(nombre__iexact=destino_nombre)
            tarifa = Tarifa.objects.get(origen=zona_origen, destino=zona_destino)

            peso_vol = calcular_peso_volumetrico(largo, ancho, alto, tarifa.factor_volumetrico)
            peso_cobrado = max(peso_real, peso_vol)

            costo_total = float(tarifa.costo_base)
            if peso_cobrado > float(tarifa.limite_peso_kg):
                exceso = peso_cobrado - float(tarifa.limite_peso_kg)
                costo_total += exceso * float(tarifa.costo_por_kg_extra)

            return JsonResponse({
                'success': True,
                'costo': round(costo_total, 2),
                'peso_cobrado': round(peso_cobrado, 2),
                'peso_volumetrico': round(peso_vol, 2),
                'moneda': 'COP'
            })
        except (Zona.DoesNotExist, Tarifa.DoesNotExist):
            return JsonResponse({'success': False, 'error': 'Zona o tarifa no definida.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    zonas = Zona.objects.all().values_list('nombre', flat=True)
    return render(request, 'cotizar.html', {'zonas': list(zonas)})


# -------------------------------
# CREAR ENVÍO
# -------------------------------
@login_required(login_url='login')
def crear_envio(request):
    if request.method == 'POST':
        numero_guia = "G-" + uuid.uuid4().hex[:10].upper()
        envio = Envio.objects.create(
            numero_guia=numero_guia,
            remitente_nombre=request.POST.get("remitente_nombre"),
            remitente_telefono=request.POST.get("remitente_telefono"),
            remitente_email=request.POST.get("remitente_email"),
            destinatario_nombre=request.POST.get("destinatario_nombre"),
            destinatario_telefono=request.POST.get("destinatario_telefono"),
            destinatario_email=request.POST.get("destinatario_email"),
            tipo_envio=request.POST.get("tipo_envio"),
            peso=request.POST.get("peso") or 0,
            dimensiones=request.POST.get("dimensiones") or "",
            direccion_origen=request.POST.get("direccion_origen"),
            direccion_destino=request.POST.get("direccion_destino"),
            estado='Creado',
            usuario=request.user
        )
        TrazaEnvio.objects.create(
            envio=envio,
            usuario=request.user,
            estado_anterior=None,
            estado_nuevo='Creado',
            descripcion='Envío creado por el usuario.',
            ubicacion=envio.direccion_origen
        )
        messages.success(request, f"Envío creado: {numero_guia}")
        return redirect("crear_envio")
    return render(request, "crear_envio.html")


# -------------------------------
# SEGUIMIENTO
# -------------------------------
def seguimiento_envio(request):
    envio, trazas, error = None, None, None
    numero_guia = request.GET.get('numero_guia')
    if numero_guia:
        try:
            envio = Envio.objects.get(numero_guia=numero_guia)
            trazas = envio.trazas.all()
        except Envio.DoesNotExist:
            error = "No se encontró un envío."
    return render(request, "seguimiento.html", {"envio": envio, "trazas": trazas, "error": error})


# -------------------------------
# SOPORTE
# -------------------------------
@login_required
def crear_ticket(request):
    if request.method == "POST":
        asunto = request.POST.get("asunto")
        mensaje = request.POST.get("mensaje")
        if not asunto or not mensaje:
            messages.error(request, "Todos los campos son obligatorios.")
            return redirect("crear_ticket")
        SoporteTicket.objects.create(
            usuario=request.user,
            asunto=asunto,
            descripcion=mensaje
        )
        messages.success(request, "✅ Ticket creado correctamente.")
        return redirect("crear_ticket")
    return render(request, "crear_ticket.html")


@login_required
def ver_tickets_admin(request):
    tickets = SoporteTicket.objects.all().order_by('-fecha')
    return render(request, 'tickets.html', {'tickets': tickets})


# -------------------------------
# RESPONDER TICKET
# -------------------------------
@login_required
def responder_ticket(request, id):
    ticket = get_object_or_404(SoporteTicket, id=id)
    if request.method == 'POST':
        mensaje = request.POST.get("mensaje")
        estado = request.POST.get("estado")
        if mensaje:
            SoporteRespuesta.objects.create(ticket=ticket, usuario=request.user, mensaje=mensaje)
        if estado:
            ticket.estado = estado
            ticket.save()
        messages.success(request, f"Ticket {ticket.id} actualizado correctamente.")
    return redirect('staff_panel')


# -------------------------------
# ACTUALIZAR ESTADO ENVÍO
# -------------------------------
@login_required
def actualizar_estado_envio(request):
    if request.method == 'POST':
        envio_id = request.POST.get("envio_id")
        nuevo_estado = request.POST.get("nuevo_estado")
        ubicacion = request.POST.get("ubicacion", "Centro de Distribución")
        detalle = request.POST.get("detalle", f"Estado actualizado a {nuevo_estado}.")
        envio = get_object_or_404(Envio, id=envio_id)
        estado_anterior = envio.estado
        TrazaEnvio.objects.create(
            envio=envio,
            usuario=request.user,
            estado_anterior=estado_anterior,
            estado_nuevo=nuevo_estado,
            descripcion=detalle,
            ubicacion=ubicacion
        )
        envio.estado = nuevo_estado
        envio.save()
        messages.success(request, f"Estado de {envio.numero_guia} actualizado a {nuevo_estado}.")
    return redirect('staff_panel')


# -------------------------------
# PDF + QR
# -------------------------------
@login_required
def descargar_guia_pdf(request, envio_id):
    try:
        if canvas is None:
            return HttpResponse("ReportLab no está instalado.", status=500)

        envio = get_object_or_404(Envio, id=envio_id)
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=guia_{envio.numero_guia}.pdf'

        # Crear canvas
        p = canvas.Canvas(response, pagesize=A6)
        ancho_pagina, alto_pagina = A6

        # Título
        p.setFont("Helvetica-Bold", 14)
        p.drawCentredString(ancho_pagina/2, alto_pagina - 40, "TRANSVERT SOLUTIONS")

        # Información del envío (tipo caja/etiqueta)
        p.setFont("Helvetica", 10)
        y = alto_pagina - 70
        linea = 15

        p.drawString(20, y, f"GUIA: {envio.numero_guia}"); y -= linea
        p.drawString(20, y, f"ESTADO: {envio.estado}"); y -= linea
        p.drawString(20, y, f"TIPO DE ENVÍO: {envio.tipo_envio}"); y -= linea

        p.drawString(20, y, "REMITENTE:"); y -= linea
        p.drawString(30, y, f"Nombre: {envio.remitente_nombre}"); y -= linea
        p.drawString(30, y, f"Teléfono: {envio.remitente_telefono}"); y -= linea
        p.drawString(30, y, f"Email: {envio.remitente_email}"); y -= linea

        p.drawString(20, y, "DESTINATARIO:"); y -= linea
        p.drawString(30, y, f"Nombre: {envio.destinatario_nombre}"); y -= linea
        p.drawString(30, y, f"Teléfono: {envio.destinatario_telefono}"); y -= linea
        p.drawString(30, y, f"Email: {envio.destinatario_email}"); y -= linea

        p.drawString(20, y, f"DIRECCIÓN ORIGEN: {envio.direccion_origen}"); y -= linea
        p.drawString(20, y, f"DIRECCIÓN DESTINO: {envio.direccion_destino}"); y -= linea
        p.drawString(20, y, f"PESO: {envio.peso} kg"); y -= linea
        p.drawString(20, y, f"DIMENSIONES: {envio.dimensiones}"); y -= linea

        # QR Code debajo de todo el texto
        qr = qrcode.make(envio.numero_guia)
        path = os.path.join(tempfile.gettempdir(), f"qr_{envio.numero_guia}.png")
        qr.save(path)
        qr_width = 100
        qr_height = 100
        p.drawImage(path, (ancho_pagina - qr_width)/2, y - qr_height - 10, qr_width, qr_height)

        p.showPage()
        p.save()

        # Limpiar archivo temporal
        if os.path.exists(path):
            os.remove(path)

        return response

    except Exception as e:
        return HttpResponse(f"Error al generar PDF: {str(e)}", status=500)

# -------------------------------
# API CREAR ENVÍO
# -------------------------------
@csrf_exempt
def crear_envio_api(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        numero_guia = "G-" + uuid.uuid4().hex[:10].upper()
        envio = Envio.objects.create(
            numero_guia=numero_guia,
            remitente_nombre=data.get('remitente_nombre'),
            remitente_telefono=data.get('remitente_telefono'),
            remitente_email=data.get('remitente_email'),
            destinatario_nombre=data.get('destinatario_nombre'),
            destinatario_telefono=data.get('destinatario_telefono'),
            destinatario_email=data.get('destinatario_email'),
            tipo_envio=data.get('tipo_envio'),
            peso=data.get('peso', 0),
            dimensiones=data.get('dimensiones', ''),
            direccion_origen=data.get('direccion_origen'),
            direccion_destino=data.get('direccion_destino'),
            estado='Creado',
            usuario=None
        )
        TrazaEnvio.objects.create(
            envio=envio,
            usuario=None,
            estado_anterior=None,
            estado_nuevo='Creado',
            descripcion='Envío creado vía API.',
            ubicacion=envio.direccion_origen
        )
        return JsonResponse({'success': True, 'numero_guia': envio.numero_guia})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# -------------------------------
# CHATBOT GEMINI
# -------------------------------
@csrf_exempt
def chatbot_response(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Solo POST permitido.'}, status=405)
    if genai is None:
        return JsonResponse({'success': False, 'error': 'Librería gemini no instalada.'}, status=500)
    try:
        data = json.loads(request.body.decode('utf-8'))
        prompt = data.get('prompt')
        if not prompt:
            return JsonResponse({'error': 'Prompt no proporcionado.'}, status=400)
        if not getattr(settings, 'GEMINI_API_KEY', None):
            return JsonResponse({'error': 'GEMINI_API_KEY no configurada.'}, status=500)
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        system_instruction = (
            "Eres el asistente virtual de Transvert Solutions, empresa colombiana de logística. "
            "Responde sobre envíos, tarifas y seguimiento con tono profesional y amigable."
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(system_instruction=system_instruction)
        )
        return JsonResponse({'success': True, 'response': response.text})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)