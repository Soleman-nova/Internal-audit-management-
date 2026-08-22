from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, Department, AuditTrail, Role


class DepartmentSerializer(serializers.ModelSerializer):
    directorate_type_display = serializers.CharField(source='get_directorate_type_display', read_only=True)
    unit_type_display = serializers.CharField(source='get_unit_type_display', read_only=True)
    children = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = '__all__'

    def get_children(self, obj):
        """Expose child departments for the org chart.

        Prefers the ``active_children`` list attached by ACTIVE_CHILDREN_PREFETCH
        (see apps/accounts/views.py). Falling back to a query keeps this correct
        for the single-object responses from create/update, where there is no
        prefetch — but on a list of 600+ units that fallback was one query per
        row, and max_page_size is 1000.
        """
        children = getattr(obj, 'active_children', None)
        if children is None:
            children = obj.children.filter(is_active=True).order_by('name')
        return [
            {
                'id': c.id,
                'name': c.name,
                'name_am': c.name_am,
                'code': c.code,
                'head': c.head,
                'head_title': c.head_title,
                'head_title_am': c.head_title_am,
                'staff_count': c.staff_count,
                'unit_type': c.unit_type,
                'unit_type_display': c.get_unit_type_display(),
                'directorate_type': c.directorate_type,
                'directorate_type_display': c.get_directorate_type_display(),
            }
            for c in children
        ]


class UserSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    full_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'full_name',
                  'role', 'department', 'department_name', 'phone', 'employee_id',
                  'is_active', 'avatar', 'avatar_url', 'created_at', 'last_login']
        read_only_fields = ['created_at', 'last_login']

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email

    def get_avatar_url(self, obj):
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
        return None


class ProfileSerializer(UserSerializer):
    """Self-service profile edits — same shape as UserSerializer, fewer writable fields.

    The response keeps the full user payload so the client can replace its
    stored user object wholesale (it needs ``role`` to keep rendering the right
    nav). But role, department, employee_id, is_active and email are pinned
    read-only: a user PATCHing their own profile must never be able to promote
    themselves or reassign their department.
    """

    class Meta(UserSerializer.Meta):
        read_only_fields = UserSerializer.Meta.read_only_fields + [
            'email', 'username', 'role', 'department', 'employee_id', 'is_active',
        ]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, required=False, allow_blank=True, default='')

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'password',
                  'confirm_password', 'role', 'department', 'phone', 'employee_id']

    def validate(self, data):
        confirm_password = data.pop('confirm_password', '')
        # Only check password match if confirm_password is provided
        if confirm_password and data['password'] != confirm_password:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        # Enforce the project's AUTH_PASSWORD_VALIDATORS on API-created accounts.
        try:
            validate_password(data['password'])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})
        return data

    def create(self, validated_data):
        # Remove confirm_password if it's still in validated_data (though validate() pops it)
        validated_data.pop('confirm_password', None)
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    employee_id = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        employee_id = data.get('employee_id')
        password = data.get('password')
        user = authenticate(employee_id=employee_id, password=password)
        if not user:
            raise serializers.ValidationError('Invalid Employee ID or password.')
        if not user.is_active:
            raise serializers.ValidationError('This account has been deactivated.')
        data['user'] = user
        return data


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class AuditTrailSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_role = serializers.CharField(source='user.role', read_only=True)

    class Meta:
        model = AuditTrail
        fields = '__all__'
