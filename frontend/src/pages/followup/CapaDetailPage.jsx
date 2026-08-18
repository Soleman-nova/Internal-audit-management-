import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { capaApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import { usePermissions } from '../../hooks/usePermissions';
import Spinner from '../../components/ui/Spinner';
import {
    ArrowLeft, AlertCircle, MessageCircle, FileText, Send,
    CalendarCheck, Paperclip, Download, ClipboardCheck
} from 'lucide-react';

const STATUS_OPTIONS = [
    'open', 'in_progress', 'partially_resolved', 'resolved',
    'not_implemented', 'closed',
];

function CapaDetailPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const toast = useToast();
    const { t } = useI18n();
    const { user, canWriteAudit, canApprovePlans } = usePermissions();

    const [capa, setCapa] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Owner response
    const [responseText, setResponseText] = useState('');
    const [statusUpdate, setStatusUpdate] = useState('in_progress');
    const [responseFile, setResponseFile] = useState(null);
    const [savingResponse, setSavingResponse] = useState(false);

    // Supervisor verification
    const [followUpDate, setFollowUpDate] = useState('');
    const [followUpNotes, setFollowUpNotes] = useState('');
    const [followUpVerified, setFollowUpVerified] = useState(false);
    const [savingFollowUp, setSavingFollowUp] = useState(false);

    // Nothing here touches state before the first await, deliberately: this runs
    // from an effect on mount, and it is also the refetch after every mutation —
    // flipping `loading` up front would blank the whole page to a spinner each
    // time the owner posted a response. `loading` starts true, only goes false.
    const fetchCapa = useCallback(async () => {
        try {
            // Single-record fetch — filtering the paginated list client-side made
            // every action past page 1 render as "not found".
            const data = await capaApi.getAction(id);
            setCapa(data);
            setStatusUpdate(data.status === 'open' ? 'in_progress' : data.status);
            setError(null);
        } catch (err) {
            const notFound = err.response?.status === 404 || err.response?.status === 403;
            setError(notFound ? 'CAPA not found' : 'Failed to load CAPA details');
            if (!notFound) toast.error('Failed to load CAPA details');
        } finally {
            setLoading(false);
        }
    }, [id, toast]);

    useEffect(() => {
        // set-state-in-effect fires because the rule cannot tell that every
        // setState in fetchCapa sits behind an await — the only synchronous path
        // into its catch would be axios throwing before it returns a promise,
        // which it does not do.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        fetchCapa();
        // fetchCapa is deliberately not a dependency: it is recreated whenever
        // `id` changes, so depending on it would be equivalent, while depending
        // on `toast` would refetch on every toast.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    // The named owner may respond even without WRITE_AUDIT — matches the
    // backend's InvolvedPartyOrCapability.for_('owner') gate on add-response.
    const isOwner = Boolean(user?.id && capa?.owner === user.id);
    const canRespond = canWriteAudit || isOwner;
    // Verification is for whoever raised the action, or an APPROVE_PLANS holder
    // — the backend applies the same object check to schedule-followup, so a
    // plain auditor would get a 403 on a colleague's CAPA.
    const canVerify = Boolean(canApprovePlans || (user?.id && capa?.assigned_by === user.id));

    const handleAddResponse = async (e) => {
        e.preventDefault();
        if (!responseText.trim()) return;
        setSavingResponse(true);
        const formData = new FormData();
        formData.append('response_text', responseText.trim());
        formData.append('status_update', statusUpdate);
        if (responseFile) formData.append('evidence_file', responseFile);
        try {
            await capaApi.addResponse(id, formData);
            setResponseText(''); setResponseFile(null);
            await fetchCapa();
            toast.success('Response recorded');
        } catch (err) {
            const msg = typeof err.response?.data === 'object'
                ? JSON.stringify(err.response.data) : 'Failed to record response';
            toast.error(msg);
        } finally {
            setSavingResponse(false);
        }
    };

    const handleScheduleFollowUp = async (e) => {
        e.preventDefault();
        if (!followUpDate) {
            toast.error('A follow-up date is required');
            return;
        }
        setSavingFollowUp(true);
        try {
            await capaApi.scheduleFollowup(id, {
                scheduled_date: followUpDate,
                notes: followUpNotes,
                status: followUpVerified ? 'completed' : 'scheduled',
                outcome: followUpVerified ? 'Implementation verified as effective' : '',
            });
            setFollowUpDate(''); setFollowUpNotes(''); setFollowUpVerified(false);
            await fetchCapa();
            toast.success('Follow-up recorded');
        } catch (err) {
            const msg = typeof err.response?.data === 'object'
                ? JSON.stringify(err.response.data) : 'Failed to record follow-up';
            toast.error(msg);
        } finally {
            setSavingFollowUp(false);
        }
    };

    const getStatusBadge = (status) => {
        switch (status) {
            case 'resolved':
            case 'closed':
                return 'badge-success';
            case 'in_progress':
            case 'partially_resolved':
                return 'badge-info';
            case 'overdue':
            case 'not_implemented':
                return 'badge-danger';
            case 'open':
                return 'badge-warning';
            default:
                return 'badge-outline';
        }
    };

    const getPriorityBadge = (priority) => {
        if (priority === 'high' || priority === 'immediate') return 'badge-danger';
        if (priority === 'medium') return 'badge-warning';
        return 'badge-success';
    };

    if (loading) {
        return (
            <div className="loading-spinner">
                <Spinner message={t('loadingCapas')} />
            </div>
        );
    }

    if (error || !capa) {
        return (
            <div className="card text-center py-12">
                <AlertCircle size={48} className="mx-auto text-danger mb-4" />
                <h3>{error || 'CAPA not found'}</h3>
                <p className="text-muted mt-2">{t('noCapaRecords')}</p>
                <Link to="/capa" className="btn btn-primary mt-6 inline-flex items-center gap-2">
                    <ArrowLeft size={16} /> {t('correctiveActions')}
                </Link>
            </div>
        );
    }

    const responses = Array.isArray(capa.responses) ? capa.responses : [];
    const followUps = Array.isArray(capa.follow_ups) ? capa.follow_ups : [];
    const effectiveDue = capa.extended_due_date || capa.due_date;

    return (
        <div className="capa-detail-view">
            {/* Back button */}
            <button
                type="button"
                className="btn btn-outline btn-sm inline-flex items-center gap-2 self-start"
                onClick={() => navigate('/capa')}
            >
                <ArrowLeft size={14} /> {t('correctiveActions')}
            </button>

            {/* Header Card */}
            <div className="card">
                <div className="flex items-start justify-between flex-wrap gap-4">
                    <div>
                        <div className="flex items-center gap-3 mb-2">
                            <span className="font-mono text-xs text-muted">{capa.action_number}</span>
                            <span className={`badge ${getPriorityBadge(capa.priority)}`}>
                                {capa.priority?.toUpperCase()}
                            </span>
                            <span className={`badge ${getStatusBadge(capa.status)}`}>
                                {capa.status?.replace('_', ' ').toUpperCase()}
                            </span>
                            {capa.is_overdue && (
                                <span className="badge badge-danger">{t('overdue').toUpperCase()}</span>
                            )}
                        </div>
                        <h2>{capa.title}</h2>
                        <p className="text-sm text-secondary mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
                            {capa.owner_name && (
                                <span className="inline-flex items-center gap-1">
                                    <FileText size={14} /> {capa.owner_name}
                                </span>
                            )}
                            {capa.finding && (
                                <Link to={`/findings/${capa.finding}`} className="inline-flex items-center gap-1 text-accent hover:underline">
                                    <AlertCircle size={14} /> {capa.finding_title || `Finding #${capa.finding}`}
                                </Link>
                            )}
                        </p>
                    </div>
                    <div className="text-right">
                        <span className="block text-xs text-muted">{t('dueDate')}</span>
                        <strong className="text-sm">{effectiveDue || '—'}</strong>
                        {capa.completed_date && (
                            <>
                                <span className="block text-xs text-muted mt-2">{t('resolvedOn')}</span>
                                <strong className="text-sm">{capa.completed_date}</strong>
                            </>
                        )}
                    </div>
                </div>
            </div>

            {/* Detail Grid */}
            <div className="capa-detail-grid">
                {/* Description */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="flex items-center gap-2">
                            <FileText size={16} className="text-accent" />
                            {t('description')}
                        </h3>
                    </div>
                    <p className="text-sm text-secondary whitespace-pre-line">{capa.description || '—'}</p>
                </div>

                {/* Recommendation */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="flex items-center gap-2">
                            <MessageCircle size={16} className="text-accent" />
                            {t('recommendation')}
                        </h3>
                    </div>
                    <p className="text-sm text-secondary whitespace-pre-line">{capa.recommendation || '—'}</p>
                </div>
            </div>

            {/* Responses */}
            <div className="card">
                <div className="card-header">
                    <h3 className="flex items-center gap-2">
                        <MessageCircle size={16} className="text-accent" />
                        {t('responses')} ({responses.length})
                    </h3>
                </div>

                {responses.length === 0 ? (
                    <p className="text-sm text-muted">{t('noResponses')}</p>
                ) : (
                    <ul className="space-y-4">
                        {responses.map(r => (
                            <li key={r.id} className="pb-4 border-b border-gray-100 dark:border-slate-800 last:border-0 last:pb-0">
                                <div className="flex items-center flex-wrap gap-2">
                                    <span className="text-sm font-medium">{r.responder_name || '—'}</span>
                                    <span className={`badge ${getStatusBadge(r.status_update)}`}>
                                        {r.status_update?.replace('_', ' ').toUpperCase()}
                                    </span>
                                    <span className="text-xs text-muted">
                                        {r.responded_at ? new Date(r.responded_at).toLocaleString() : ''}
                                    </span>
                                </div>
                                <p className="text-sm text-secondary mt-1 whitespace-pre-line">{r.response_text}</p>
                                {r.evidence_file && (
                                    <a
                                        href={r.evidence_file}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="btn btn-outline btn-sm inline-flex items-center gap-1 mt-2"
                                    >
                                        <Download size={12} /> {t('download')}
                                    </a>
                                )}
                            </li>
                        ))}
                    </ul>
                )}

                {canRespond && capa.status !== 'closed' && (
                    <form onSubmit={handleAddResponse} className="mt-4 pt-4 border-t border-gray-200 dark:border-slate-800 space-y-3">
                        <textarea
                            className="form-input w-full"
                            rows={3}
                            placeholder={t('progressUpdate')}
                            value={responseText}
                            onChange={(e) => setResponseText(e.target.value)}
                        />
                        <div className="flex flex-wrap gap-3 items-center">
                            <label className="text-xs text-muted">{t('newStatus')}</label>
                            <select
                                className="form-input"
                                value={statusUpdate}
                                onChange={(e) => setStatusUpdate(e.target.value)}
                            >
                                {STATUS_OPTIONS.map(s => (
                                    <option key={s} value={s}>{s.replace('_', ' ')}</option>
                                ))}
                            </select>
                            <label className="text-xs text-muted inline-flex items-center gap-1">
                                <Paperclip size={12} /> {t('attachmentOptional')}
                            </label>
                            <input
                                type="file"
                                className="form-input flex-1"
                                onChange={(e) => setResponseFile(e.target.files?.[0] || null)}
                            />
                        </div>
                        <button
                            type="submit"
                            className="btn btn-primary btn-sm inline-flex items-center gap-2"
                            disabled={savingResponse || !responseText.trim()}
                        >
                            <Send size={14} /> {savingResponse ? t('loading') : t('submitResponse')}
                        </button>
                    </form>
                )}
            </div>

            {/* Follow-ups — verification visits by a supervisor or manager */}
            <div className="card">
                <div className="card-header">
                    <h3 className="flex items-center gap-2">
                        <CalendarCheck size={16} className="text-accent" />
                        {t('followUps')} ({followUps.length})
                    </h3>
                </div>

                {followUps.length === 0 ? (
                    <p className="text-sm text-muted">{t('noFollowUps')}</p>
                ) : (
                    <ul className="space-y-3">
                        {followUps.map(f => (
                            <li key={f.id} className="pb-3 border-b border-gray-100 dark:border-slate-800 last:border-0 last:pb-0">
                                <div className="flex items-center flex-wrap gap-2">
                                    <strong className="text-sm">{f.scheduled_date}</strong>
                                    <span className={`badge ${f.status === 'completed' ? 'badge-success' : 'badge-info'}`}>
                                        {f.status?.toUpperCase()}
                                    </span>
                                    <span className="text-xs text-muted">{f.conducted_by_name || '—'}</span>
                                </div>
                                {f.outcome && <p className="text-sm font-medium mt-1">{f.outcome}</p>}
                                {f.notes && <p className="text-sm text-secondary mt-1 whitespace-pre-line">{f.notes}</p>}
                            </li>
                        ))}
                    </ul>
                )}

                {canVerify && (
                    <form onSubmit={handleScheduleFollowUp} className="mt-4 pt-4 border-t border-gray-200 dark:border-slate-800 space-y-3">
                        <div className="flex flex-wrap gap-3 items-center">
                            <label className="text-xs text-muted">{t('followUpDate')}</label>
                            <input
                                type="date"
                                className="form-input"
                                value={followUpDate}
                                onChange={(e) => setFollowUpDate(e.target.value)}
                            />
                            <label className="text-xs text-muted inline-flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    checked={followUpVerified}
                                    onChange={(e) => setFollowUpVerified(e.target.checked)}
                                />
                                {t('isVerified')}
                            </label>
                        </div>
                        <textarea
                            className="form-input w-full"
                            rows={2}
                            placeholder={t('followUpFindings')}
                            value={followUpNotes}
                            onChange={(e) => setFollowUpNotes(e.target.value)}
                        />
                        <button
                            type="submit"
                            className="btn btn-primary btn-sm inline-flex items-center gap-2"
                            disabled={savingFollowUp}
                        >
                            <ClipboardCheck size={14} /> {savingFollowUp ? t('loading') : t('verifyAndSchedule')}
                        </button>
                    </form>
                )}
            </div>
        </div>
    );
}

export default CapaDetailPage;
