"""Shared upload validation.

`Evidence.file`, `WorkingPaper.file`, and `User.avatar` were bare file fields:
no extension allowlist, no size cap, and no ``DATA_UPLOAD_MAX_MEMORY_SIZE`` in
settings. Auditees can reach ``upload-evidence`` by design, so that combination
let any authenticated user store a file of any type and any size.

Kept as module-level callables (not lambdas or closures) because Django
serializes field validators into migrations and needs an importable reference.
"""
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

# Formats an audit function actually attaches: office documents, PDFs, plain
# text/CSV exports, images of physical records, and the two archive formats
# people use to bundle a folder of scans.
DOCUMENT_EXTENSIONS = (
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'csv', 'rtf', 'odt', 'ods',
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tif', 'tiff', 'webp',
    'zip', '7z',
)

IMAGE_EXTENSIONS = ('png', 'jpg', 'jpeg', 'gif', 'webp')

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024   # 10 MB
MAX_IMAGE_SIZE = 2 * 1024 * 1024       # 2 MB


@deconstructible
class UploadValidator:
    """Reject uploads by extension or size.

    Extension matching only — content sniffing would need python-magic, and the
    real defence against a hostile file is that nothing is ever served from
    MEDIA_ROOT directly (see EvidenceViewSet.download).
    """

    def __init__(self, extensions=DOCUMENT_EXTENSIONS, max_bytes=MAX_DOCUMENT_SIZE):
        self.extensions = tuple(extensions)
        self.max_bytes = max_bytes

    def __call__(self, value):
        name = getattr(value, 'name', '') or ''
        extension = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if extension not in self.extensions:
            raise ValidationError(
                '“%(ext)s” files are not accepted. Allowed types: %(allowed)s.',
                code='invalid_extension',
                params={'ext': extension or name, 'allowed': ', '.join(self.extensions)},
            )
        size = getattr(value, 'size', None)
        if size is not None and size > self.max_bytes:
            raise ValidationError(
                'File is %(size).1f MB; the limit is %(limit).1f MB.',
                code='file_too_large',
                params={
                    'size': size / (1024 * 1024),
                    'limit': self.max_bytes / (1024 * 1024),
                },
            )

    def __eq__(self, other):
        return (
            isinstance(other, UploadValidator)
            and self.extensions == other.extensions
            and self.max_bytes == other.max_bytes
        )

    # Defining __eq__ would otherwise set __hash__ to None. Django compares
    # validators when deciding whether a field changed (so makemigrations does
    # not emit an identical migration on every run) and puts them in sets while
    # deconstructing, which needs both.
    def __hash__(self):
        return hash((self.extensions, self.max_bytes))


validate_document_upload = UploadValidator()
validate_image_upload = UploadValidator(IMAGE_EXTENSIONS, MAX_IMAGE_SIZE)
