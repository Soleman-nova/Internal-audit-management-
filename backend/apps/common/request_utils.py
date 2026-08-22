"""Helpers for nested-route request payloads.

Several ``@action`` routes carry the parent object in the URL but hand the
payload to a serializer that still declares that parent required. The idiom was
``request.data.copy()`` followed by an assignment — and on a multipart request
that copy is a ``deepcopy``, which raises

    TypeError: cannot pickle 'BufferedRandom' instances

as soon as the upload is large enough for Django to spool it to a
``TemporaryUploadedFile`` instead of holding it in memory. That made every
evidence upload above ``FILE_UPLOAD_MAX_MEMORY_SIZE`` a 500, which is precisely
the size of file an auditee attaches when the evidence is a scan.
"""


def with_parent(data, **parents):
    """``data`` as a plain dict, with ``parents`` written over the top.

    ``QueryDict.dict()`` reads the last value for each key — the same thing
    ``QueryDict[key]`` returns and the same thing the serializer would have seen
    — while leaving uploaded files as the very objects the parser produced,
    unpickled and unread. Note that ``{**querydict}`` would *not* do: a
    ``MultiValueDict`` keeps its values in lists internally and dict-unpacking
    reads that storage directly, so every value would arrive wrapped in a list.

    JSON payloads parse to an ordinary ``dict``, which has no ``.dict()``; those
    are copied shallowly instead.
    """
    plain = data.dict() if hasattr(data, 'dict') else dict(data)
    plain.update(parents)
    return plain
