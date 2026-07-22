from rest_framework import serializers


class LiveHealthSerializer(serializers.Serializer[dict[str, str]]):
    status = serializers.CharField()
    service = serializers.CharField()


class ReadyHealthSerializer(serializers.Serializer[dict[str, object]]):
    status = serializers.CharField()
    checks = serializers.DictField(child=serializers.CharField())
