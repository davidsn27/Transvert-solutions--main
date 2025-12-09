from django.db import models
from django.contrib.auth.models import User


# -------------------------------
# MODELO: SOPORTE - TICKET
# -------------------------------
class SoporteTicket(models.Model):

    PRIORIDAD_CHOICES = [
        ('Baja', 'Baja'),
        ('Media', 'Media'),
        ('Alta', 'Alta')
    ]

    ESTADO_CHOICES = [
        ('Pendiente', 'Pendiente'),
        ('En proceso', 'En proceso'),
        ('Respondido', 'Respondido')
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    asunto = models.CharField(max_length=200)
    descripcion = models.TextField()

    correo = models.EmailField(max_length=255, blank=True, null=True)

    prioridad = models.CharField(
        max_length=10,
        choices=PRIORIDAD_CHOICES,
        default='Media'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default="Pendiente"
    )

    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ticket #{self.id} - {self.asunto}"


# -------------------------------
# MODELO: SOPORTE - RESPUESTA
# -------------------------------
class SoporteRespuesta(models.Model):

    ticket = models.ForeignKey(
        SoporteTicket,
        on_delete=models.CASCADE,
        related_name="respuestas"
    )

    usuario = models.ForeignKey(User, on_delete=models.CASCADE)

    mensaje = models.TextField()

    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Respuesta de {self.usuario.username} al ticket {self.ticket.id}"


# -------------------------------
# MODELO: ENVÍO
# -------------------------------
class Envio(models.Model):

    ESTADOS = (
        ('Creado', 'Creado'),
        ('Recogido', 'Recogido'),
        ('En Clasificación', 'En Clasificación'),
        ('En Ruta', 'En Ruta'),
        ('En Reparto', 'En Reparto'),
        ('Entregado', 'Entregado'),
        ('Excepción', 'Excepción'),
        ('Cancelado', 'Cancelado'),
    )

    numero_guia = models.CharField(max_length=20, unique=True)
    
    # Remitente
    remitente_nombre = models.CharField(max_length=100)
    remitente_telefono = models.CharField(max_length=20)
    remitente_email = models.EmailField(blank=True, null=True)

    # Destinatario
    destinatario_nombre = models.CharField(max_length=100)
    destinatario_telefono = models.CharField(max_length=20)
    destinatario_email = models.EmailField(blank=True, null=True)

    # Envío
    tipo_envio = models.CharField(max_length=20)
    peso = models.DecimalField(max_digits=10, decimal_places=2)
    dimensiones = models.CharField(max_length=100, blank=True, null=True)

    # Direcciones
    direccion_origen = models.CharField(max_length=200)
    direccion_destino = models.CharField(max_length=200)

    # Estado del envío
    estado = models.CharField(max_length=20, choices=ESTADOS, default="Creado")
    
    # Vínculo al usuario
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    fecha_creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.numero_guia
    
    class Meta:
        verbose_name = "Envío"
        verbose_name_plural = "Envíos"


# -------------------------------
# TRAZABILIDAD
# -------------------------------
class TrazaEnvio(models.Model):
    
    envio = models.ForeignKey(Envio, on_delete=models.CASCADE, related_name='trazas')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    estado_anterior = models.CharField(max_length=50, blank=True, null=True)
    estado_nuevo = models.CharField(max_length=50, choices=Envio.ESTADOS)
    descripcion = models.TextField(verbose_name="Detalle del Evento")
    ubicacion = models.CharField(max_length=100, verbose_name="Ubicación")
    fecha_hora = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Traza del Envío"
        verbose_name_plural = "Trazas del Envío"
        ordering = ['fecha_hora']

    def __str__(self):
        return f'{self.envio.numero_guia} - {self.estado_nuevo} en {self.ubicacion}'


# -------------------------------
# ZONA / CIUDAD
# -------------------------------
class Zona(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Zona/Ciudad"
        verbose_name_plural = "Zonas/Ciudades"


# -------------------------------
# TARIFA
# -------------------------------
class Tarifa(models.Model):
    origen = models.ForeignKey(Zona, on_delete=models.CASCADE, related_name='tarifas_origen')
    destino = models.ForeignKey(Zona, on_delete=models.CASCADE, related_name='tarifas_destino')
    
    factor_volumetrico = models.IntegerField(default=5000)
    costo_base = models.DecimalField(max_digits=10, decimal_places=2)
    limite_peso_kg = models.DecimalField(max_digits=10, decimal_places=2, default=5.0)
    costo_por_kg_extra = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        unique_together = ('origen', 'destino') 
        verbose_name = "Tarifa de Envío"
        verbose_name_plural = "Tarifas de Envío"

    def __str__(self):
        return f'Tarifa de {self.origen} a {self.destino}'