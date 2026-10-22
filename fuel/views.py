from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import FuelStation


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok', 'stations': FuelStation.objects.count()})
