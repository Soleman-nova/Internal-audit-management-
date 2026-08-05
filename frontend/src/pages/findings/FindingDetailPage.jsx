import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { findingsApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import { ArrowLeft, AlertTriangle, FileText, MessageCircle, CheckCircle2, XCircle } from 'lucide-react';

function FindingDetailPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const toast = useToast();
    const { t } = useI18n();
    const [finding, setFinding] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetchFinding();
        // eslint-disable-next-line
    }, [id]);

    const fetchFinding = async () => {
        setLoading(true);
        setError(null);
        try {
            const list = await findingsApi.getFindings();
            const items = Array.isArray(list) ? list : [];
            const found = items.find(f => f.id.toString() === id.toString());
            if (found) {
                setFinding(found);
            } else {
                setError('Finding not found');
            }
        } catch (err) {
            setError('Failed to load finding details');
            toast.error('Failed to load finding details');
        } finally {
            setLoading(false);
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
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <Link to="/findings" className="btn btn-outline btn-sm">
                            {t('listView')}
                        </Link>
                    </div>
                </div>
            </div>

            {/* Detail Sections */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                        <FileText className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                        {t('descriptionLabel')}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{finding.description || '—'}</p>
                </div>

                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-amber-500" />
                        {t('conditionLabel')}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{finding.condition || '—'}</p>
                </div>

                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-blue-500" />
                        {t('criteriaLabel')}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{finding.criteria || '—'}</p>
                </div>

                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                        <XCircle className="w-4 h-4 text-rose-500" />
                        {t('causeLabel')}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{finding.cause || '—'}</p>
                </div>

                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-orange-500" />
                        {t('effectLabel')}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{finding.effect || '—'}</p>
                </div>

                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                        <MessageCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                        {t('recommendationLabel')}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{finding.recommendation || '—'}</p>
                </div>
            </div>
        </div>
    );
}

export default FindingDetailPage;