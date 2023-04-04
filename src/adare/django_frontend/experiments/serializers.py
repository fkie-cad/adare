# external imports
from rest_framework import serializers
from rest_framework.renderers import JSONRenderer

# internal imports
from adare.django_frontend.experiments.models import Experiment, Test, OsInfo, Status, Tool, TestFunction, Result, TestParameterEntries, TestParameter


class StatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Status
        exclude = ('id',)


class OsInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = OsInfo
        exclude = ('id',)


class ToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tool
        exclude = ('id',)


class ResultSerializer(serializers.ModelSerializer):
    status = StatusSerializer(read_only=True)
    class Meta:
        model = Result
        exclude = ('id',)


class TestParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestParameter
        exclude = ('id',)


class TestParameterEntriesSerializer(serializers.ModelSerializer):
    parameter = TestParameterSerializer()

    class Meta:
        model = TestParameterEntries
        exclude = ('id',)


class TestFunctionSerializer(serializers.ModelSerializer):
    possible_parameters = TestParameterSerializer(many=True, read_only=True)

    class Meta:
        model = TestFunction
        exclude = ('id',)


class TestSerializer(serializers.ModelSerializer):
    testfunction = TestFunctionSerializer(read_only=True)
    result = ResultSerializer(read_only=True)
    parameters = TestParameterEntriesSerializer(many=True, read_only=True)
    tool = ToolSerializer(read_only=True)

    class Meta:
        model = Test
        fields = '__all__'


class ExperimentSerializer(serializers.ModelSerializer):
    tests = TestSerializer(many=True, read_only=True)
    os_info = OsInfoSerializer(read_only=True)
    status = StatusSerializer(read_only=True)

    class Meta:
        model = Experiment
        fields = [
            'uuid',
            'name',
            'timestamp_start',
            'timestamp_end',
            'tests',
            'os_info',
            'description',
            'status'
        ]

    def to_json(self):
        return JSONRenderer().render(self.data)