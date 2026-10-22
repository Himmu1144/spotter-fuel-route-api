from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import FuelStation
from .places import PlaceNotFound
from .planner import TripNotFeasible, plan_trip
from .routing import RouteNotFound, RoutingUnavailable
from .serializers import RouteQuerySerializer

ERRORS = {
    PlaceNotFound: (status.HTTP_400_BAD_REQUEST, 'place_not_found'),
    RouteNotFound: (status.HTTP_422_UNPROCESSABLE_ENTITY, 'no_route'),
    TripNotFeasible: (status.HTTP_422_UNPROCESSABLE_ENTITY, 'no_fuel_in_range'),
    RoutingUnavailable: (status.HTTP_502_BAD_GATEWAY, 'routing_unavailable'),
}


def error(http_status, code, message):
    return Response({'error': {'code': code, 'message': message}}, status=http_status)


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok', 'stations': FuelStation.objects.count()})


@api_view(['GET'])
def route(request):
    """Plan a trip: GET /api/route/?start=Chicago, IL&finish=Denver, CO[&mode=cheapest]"""
    query = RouteQuerySerializer(data=request.query_params)
    if not query.is_valid():
        fields = '; '.join(f'{name}: {" ".join(problems)}' for name, problems in query.errors.items())
        return error(status.HTTP_400_BAD_REQUEST, 'invalid_input', fields)
    params = query.validated_data
    try:
        plan = plan_trip(params['start'], params['finish'], params['mode'])
    except tuple(ERRORS) as problem:
        http_status, code = ERRORS[type(problem)]
        return error(http_status, code, str(problem))
    map_url = request.build_absolute_uri(f'{reverse("map")}?{urlencode(params)}')
    return Response({'map_url': map_url, **plan})


def route_map(request):
    """A page that draws a plan from the API on a Leaflet map."""
    return render(request, 'fuel/map.html')
