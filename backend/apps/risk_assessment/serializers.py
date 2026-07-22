from rest_framework import serializers
from .models import RiskParameter, RiskAssessment, SelfAssessment
from apps.accounts.serializers import UserSerializer


class RiskParameterSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = RiskParameter
        fields = '__all__'


class SelfAssessmentSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.CharField(source='submitted_by.full_name', read_only=True)

    class Meta:
        model = SelfAssessment
        fields = '__all__'


class RiskAssessmentSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    assessed_by_name = serializers.CharField(source='assessed_by.full_name', read_only=True)
    risk_rating_display = serializers.CharField(source='get_risk_rating_display', read_only=True)
    self_assessment = SelfAssessmentSerializer(read_only=True)

    class Meta:
        model = RiskAssessment
        fields = '__all__'
        read_only_fields = ['risk_score', 'risk_rating', 'residual_risk']
