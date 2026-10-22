from rest_framework import serializers


class RouteQuerySerializer(serializers.Serializer):
    start = serializers.CharField(help_text='"City, ST", "City, State" or "lat,lon"')
    finish = serializers.CharField(help_text='"City, ST", "City, State" or "lat,lon"')
    mode = serializers.ChoiceField(choices=['balanced', 'cheapest'], default='balanced')
