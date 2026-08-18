import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { findingsApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import { usePermissions } from '../../hooks/usePermissions';
import Spinner from '../../components/ui/Spinner';
import {
    ArrowLeft, AlertTriangle, FileText, MessageCircle, CheckCircle2, XCircle,
    Paperclip, Upload, Send, RotateCcw, Lock, Download, User as UserIcon
} from 'lucide-react';

function FindingDetailPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const toast = useToast();
    const { t } = useI18n();
    const { user, canWriteAudit, canCloseFindings } = usePermissions();

    const [finding, setFinding] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Discussion
    const [comment, setComment] = useState('');
    const [postingComment, setPostingComment] = useState(false);

    // Evidence
    const [evTitle, setEvTitle] = useState('');
    const [evType, setEvType] = useState('document');
    const [evFile, setEvFile] = useState(null);
    const [uploading, setUploading] = useState(false);

    // Lifecycle
    const [actionBusy, setActionBusy] = useState('');

    // Nothing here touches state before the first await, deliberately: this runs
    // from an effect on mount, and it is also the refetch after every mutation —
    // flipping `loading` up front would blank the whole page to a spinner each
    // time you posted a comment. `loading` starts true and only ever goes false.
    const fetchFinding = useCallback(async () => {
        try {
            // Single-record fetch: filtering the paginated list client-side made
            // every record past page 1 render as "not found".
            const data = await findingsApi.getFinding(id);
            setFinding(data);
            setError(null);
        } catch (err) {
            const notFound = err.response?.status === 404 || err.response?.status === 403;
            setError(notFound ? 'Finding not found' : 'Failed to load finding details');
            if (!notFound) toast.error('Failed to load finding details');
        } finally {
            setLoading(false);
        }
    }, [id, toast]);

    useEffect(() => {
        // set-state-in-effect fires because the rule cannot tell that every
        // setState in fetchFinding sits behind an await — the only synchronous
        // path into its catch would be axios throwing before it returns a
        // promise, which it does not do.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        fetchFinding();
        // fetchFinding is deliberately not a dependency: it is recreated whenever
        // `id` changes, so depending on it would be equivalent, while depending
        // on `toast` would refetch on every toast.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    // The auditee named on the record may comment, attach evidence and dispute,
    // even though they hold no capabilities — mirrors the backend's
    // InvolvedPartyOrCapability gate so the UI never offers a button that 403s.
    const isInvolvedParty = Boolean(
        user?.id && (finding?.auditee === user.id || finding?.assigned_to === user.id)
    );
    const canDiscuss = canWriteAudit || isInvolvedParty;
    const isClosed = finding?.status === 'closed';

    const handleAddComment = async (e) => {
        e.preventDefault();
        if (!comment.trim()) return;
        setPostingComment(true);
        try {
            await findingsApi.addComment(id, comment.trim());
            setComment('');
            await fetchFinding();
            toast.success('Comment posted');
        } catch (err) {
            const msg = typeof err.response?.data === 'object'
                ? JSON.stringify(err.response.data) : 'Failed to post comment';
            toast.error(msg);
        } finally {
            setPostingComment(false);
        }
    };

    const handleUploadEvidence = async (e) => {
        e.preventDefault();
        if (!evFile || !evTitle.trim()) {
            toast.error('A title and a file are both required');
            return;
        }
        setUploading(true);
        const formData = new FormData();
        formData.append('title', evTitle.trim());
        formData.append('evidence_type', evType);
        formData.append('file', evFile);
        try {
            await findingsApi.uploadEvidence(id, formData);
            setEvTitle(''); setEvFile(null); setEvType('document');
            await fetchFinding();
            toast.success('Evidence attached');
        } catch (err) {
            const msg = typeof err.response?.data === 'object'
                ? JSON.stringify(err.response.data) : 'Failed to attach evidence';
            toast.error(msg);
        } finally {
            setUploading(false);
        }
    };

    // Every transition goes through its own endpoint so the server stamps the
    // resolution date, writes the audit trail and notifies the right party.
    const runTransition = async (key, call, successMsg) => {
        setActionBusy(key);
        try {
            await call(id);
            await fetchFinding();
            toast.success(successMsg);
        } catch (err) {
            const msg = typeof err.response?.data === 'object'
                ? JSON.stringify(err.response.data) : `Failed to ${key} finding`;
            toast.error(msg);
        } finally {
            setActionBusy('');
        }
    };

    const getSeverityClass = (severity) => {
        switch (severity) {
            case 'critical': return 'badge-danger';
            case 'high': return 'badge-warning';
            case 'medium': return 'badge-info';
            default: return 'badge-success';
        }
    };

    const getStatusClass = (status) => {
        switch (status) {
            case 'resolved':
            case 'closed':
                return 'badge-success';
            case 'in_progress':
                return 'badge-info';
            case 'disputed':
                return 'badge-danger';
            case 'open':
                return 'badge-warning';
            default:
                return 'badge-outline';
        }
    };

    if (loading) {
        return (
            <div className="flex justify-center py-16">
                <Spinner message={t('loadingFindings')} />
            </div>
        );
    }

    if (error || !finding) {
        return (
            <div className="card text-center py-12">
                <AlertTriangle className="w-12 h-12 mx-auto text-amber-500 mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{error || 'Finding not found'}</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">{t('noFindingsForAudit')}</p>
                <Link to="/findings" className="btn btn-primary mt-6 inline-flex items-center gap-2">
                    <ArrowLeft className="w-4 h-4" /> {t('findingsRegistry')}
                </Link>
            </div>
        );
    }

    const comments = Array.isArray(finding.comments) ? finding.comments : [];
    const evidence = Array.isArray(finding.evidence) ? finding.evidence : [];

    const sections = [
        { key: 'description', icon: <FileText className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />, label: t('descriptionLabel'), value: finding.description },
        { key: 'condition', icon: <AlertTriangle className="w-4 h-4 text-amber-500" />, label: t('conditionLabel'), value: finding.condition },
        { key: 'criteria', icon: <CheckCircle2 className="w-4 h-4 text-blue-500" />, label: t('criteriaLabel'), value: finding.criteria },
        { key: 'cause', icon: <XCircle className="w-4 h-4 text-rose-500" />, label: t('causeLabel'), value: finding.cause },
        { key: 'effect', icon: <AlertTriangle className="w-4 h-4 text-orange-500" />, label: t('effectLabel'), value: finding.effect },
        { key: 'recommendation', icon: <MessageCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />, label: t('recommendationLabel'), value: finding.recommendation },
        { key: 'management_response', icon: <UserIcon className="w-4 h-4 text-indigo-500" />, label: t('managementResponse'), value: finding.management_response },
    ];

    return (
        <div className="space-y-6">
            {/* Back button */}
            <button
                onClick={() => navigate('/findings')}
                className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
                <ArrowLeft className="w-4 h-4" /> {t('findingsRegistry')}
            </button>

            {/* Header Card */}
            <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                <div className="flex items-start justify-between flex-wrap gap-4">
                    <div>
                        <div className="flex items-center gap-3 mb-2">
                            <span className="text-xs font-mono text-gray-500 dark:text-gray-400">{finding.finding_number}</span>
                            <span className={`badge ${getSeverityClass(finding.severity)}`}>
                                {finding.severity?.toUpperCase()}
                            </span>
                            <span className={`badge ${getStatusClass(finding.status)}`}>
                                {finding.status?.replace('_', ' ').toUpperCase()}
                            </span>
                        </div>
                        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{finding.title}</h1>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                            {finding.category?.replace('_', ' ').toUpperCase()}
                            {finding.engagement_title ? ` · ${finding.engagement_title}` : ''}
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <Link to="/findings" className="btn btn-outline btn-sm">
                            {t('listView')}
                        </Link>
                    </div>
                </div>

                {/* Facts strip */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-6 border-t border-gray-200 dark:border-slate-800">
                    {[
                        [t('identifiedBy'), finding.identified_by_name],
                        [t('assignedTo'), finding.assigned_to_name],
                        [t('auditeeContact'), finding.auditee_name],
                        [finding.actual_resolution_date ? t('resolvedOn') : t('targetDate'),
                            finding.actual_resolution_date || finding.target_resolution_date],
                    ].map(([label, value]) => (
                        <div key={label}>
                            <span className="block text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">{label}</span>
                            <strong className="text-sm text-gray-900 dark:text-white">{value || '—'}</strong>
                        </div>
                    ))}
                </div>

                {/* Lifecycle action bar — each button mirrors a backend gate */}
                {(canCloseFindings || canDiscuss) && (
                    <div className="flex flex-wrap items-center gap-2 mt-6 pt-6 border-t border-gray-200 dark:border-slate-800">
                        <span className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500 mr-1">
                            {t('lifecycle')}
                        </span>
                        {canCloseFindings && !isClosed && finding.status !== 'resolved' && (
                            <button
                                type="button"
                                className="btn btn-outline btn-sm inline-flex items-center gap-2"
                                disabled={Boolean(actionBusy)}
                                onClick={() => runTransition('resolve', findingsApi.resolveFinding, 'Finding marked as resolved')}
                            >
                                <CheckCircle2 className="w-4 h-4" /> {t('resolve')}
                            </button>
                        )}
                        {canCloseFindings && !isClosed && (
                            <button
                                type="button"
                                className="btn btn-primary btn-sm inline-flex items-center gap-2"
                                disabled={Boolean(actionBusy)}
                                onClick={() => runTransition('close', findingsApi.closeFinding, 'Finding closed')}
                            >
                                <Lock className="w-4 h-4" /> {t('closeFinding')}
                            </button>
                        )}
                        {canCloseFindings && ['resolved', 'closed', 'disputed'].includes(finding.status) && (
                            <button
                                type="button"
                                className="btn btn-outline btn-sm inline-flex items-center gap-2"
                                disabled={Boolean(actionBusy)}
                                onClick={() => runTransition('reopen', findingsApi.reopenFinding, 'Finding reopened')}
                            >
                                <RotateCcw className="w-4 h-4" /> {t('reopen')}
                            </button>
                        )}
                        {canDiscuss && !isClosed && finding.status !== 'disputed' && (
                            <button
                                type="button"
                                className="btn btn-outline btn-sm inline-flex items-center gap-2 text-rose-600 dark:text-rose-400"
                                disabled={Boolean(actionBusy)}
                                onClick={() => runTransition('dispute', findingsApi.disputeFinding, 'Finding disputed')}
                            >
                                <XCircle className="w-4 h-4" /> {t('dispute')}
                            </button>
                        )}
                    </div>
                )}
            </div>

            {/* Detail Sections */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {sections.map(({ key, icon, label, value }) => (
                    <div key={key} className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                            {icon}{label}
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed whitespace-pre-line">{value || '—'}</p>
                    </div>
                ))}
            </div>

            {/* Evidence + Discussion */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Evidence */}
                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                        <Paperclip className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                        {t('evidenceLabel')} ({evidence.length})
                    </h3>

                    {evidence.length === 0 ? (
                        <p className="text-sm text-gray-500 dark:text-gray-400">{t('noEvidence')}</p>
                    ) : (
                        <ul className="space-y-2">
                            {evidence.map(ev => (
                                <li key={ev.id} className="flex items-center justify-between gap-3 py-2 border-b border-gray-100 dark:border-slate-800 last:border-0">
                                    <div className="min-w-0">
                                        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{ev.title}</p>
                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                            {ev.evidence_type} · {ev.uploaded_by_name || '—'}
                                            {ev.uploaded_at ? ` · ${new Date(ev.uploaded_at).toLocaleDateString()}` : ''}
                                        </p>
                                    </div>
                                    {ev.file_url && (
                                        <a
                                            href={ev.file_url}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="btn btn-outline btn-sm inline-flex items-center gap-1 shrink-0"
                                        >
                                            <Download className="w-3.5 h-3.5" /> {t('download')}
                                        </a>
                                    )}
                                </li>
                            ))}
                        </ul>
                    )}

                    {canDiscuss && !isClosed && (
                        <form onSubmit={handleUploadEvidence} className="mt-4 pt-4 border-t border-gray-200 dark:border-slate-800 space-y-3">
                            <input
                                type="text"
                                className="form-input w-full"
                                placeholder={t('evidenceTitle')}
                                value={evTitle}
                                onChange={(e) => setEvTitle(e.target.value)}
                            />
                            <div className="flex flex-wrap gap-3">
                                <select
                                    className="form-input"
                                    value={evType}
                                    onChange={(e) => setEvType(e.target.value)}
                                >
                                    <option value="document">Document</option>
                                    <option value="screenshot">Screenshot</option>
                                    <option value="spreadsheet">Spreadsheet</option>
                                    <option value="photo">Photo</option>
                                    <option value="video">Video</option>
                                    <option value="other">Other</option>
                                </select>
                                <input
                                    type="file"
                                    className="form-input flex-1"
                                    onChange={(e) => setEvFile(e.target.files?.[0] || null)}
                                />
                            </div>
                            <button type="submit" className="btn btn-primary btn-sm inline-flex items-center gap-2" disabled={uploading}>
                                <Upload className="w-4 h-4" /> {uploading ? t('loading') : t('attachEvidence')}
                            </button>
                        </form>
                    )}
                </div>

                {/* Discussion */}
                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                        <MessageCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                        {t('discussion')} ({comments.length})
                    </h3>

                    {comments.length === 0 ? (
                        <p className="text-sm text-gray-500 dark:text-gray-400">{t('noComments')}</p>
                    ) : (
                        <ul className="space-y-4 max-h-80 overflow-y-auto pr-1">
                            {comments.map(c => (
                                <li key={c.id} className="text-sm">
                                    <div className="flex items-center gap-2">
                                        <span className="font-medium text-gray-900 dark:text-white">{c.author_name || '—'}</span>
                                        <span className="text-xs text-gray-400 dark:text-gray-500">
                                            {c.created_at ? new Date(c.created_at).toLocaleString() : ''}
                                        </span>
                                    </div>
                                    <p className="text-gray-600 dark:text-gray-300 mt-1 whitespace-pre-line">{c.comment}</p>
                                </li>
                            ))}
                        </ul>
                    )}

                    {canDiscuss && !isClosed && (
                        <form onSubmit={handleAddComment} className="mt-4 pt-4 border-t border-gray-200 dark:border-slate-800 space-y-3">
                            <textarea
                                className="form-input w-full"
                                rows={3}
                                placeholder={t('writeComment')}
                                value={comment}
                                onChange={(e) => setComment(e.target.value)}
                            />
                            <button
                                type="submit"
                                className="btn btn-primary btn-sm inline-flex items-center gap-2"
                                disabled={postingComment || !comment.trim()}
                            >
                                <Send className="w-4 h-4" /> {postingComment ? t('loading') : t('postComment')}
                            </button>
                        </form>
                    )}
                </div>
            </div>
        </div>
    );
}

export default FindingDetailPage;
