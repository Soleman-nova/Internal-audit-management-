import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { capaApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import { ArrowLeft, CheckCircle2, Clock, AlertCircle, MessageCircle, FileText } from 'lucide-react';

function CapaDetailPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const toast = useToast();
    const { t } = useI18n();
    const [capa, setCapa] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetchCapa();
        // eslint-disable-next-line
    }, [id]);

    const fetchCapa = async () => {
        setLoading(true);
        setError(null);
        try {
            const list = await capaApi.getActions();
            const items = Array.isArray(list) ? list : [];
            const found = items.find(c => c.id.toString() === id.toString());
            if (found) {
                setCapa(found);
            } else {
                setError('CAPA not found');
            }
        } catch (err) {
            setError('Failed to load CAPA details');
            toast.error('Failed to load CAPA details');
        } finally {
            setLoading(false);
        }
    };

    const getStatusBadge = (status) => {
        switch (status) {
            case 'resolved':
            case 'closed':
                return 'badge-success';
            case 'in_progress':
                return 'badge-info';
            case 'overdue':
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
            <div className="flex justify-center py-16">
                <Spinner message={t('loadingCapas')} />
            </div>
        );
    }

    if (error || !capa) {
        return (
            <div className="card text-center py-12">
                <AlertCircle className="w-12 h-12 mx-auto text-rose-500 mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{error || 'CAPA not found'}</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">{t('noCapaRecords')}</p>
                <Link to="/capa" className="btn btn-primary mt-6 inline-flex items-center gap-2">
                    <ArrowLeft className="w-4 h-4" /> {t('correctiveActions')}
                </Link>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Back button */}
            <button
                onClick={() => navigate('/capa')}
                className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
                <ArrowLeft className="w-4 h-4" /> {t('correctiveActions')}
            </button>

            {/* Header Card */}
            <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                <div className="flex items-start justify-between flex-wrap gap-4">
                    <div>
                        <div className="flex items-center gap-3 mb-2">
                            <span className="text-xs font-mono text-gray-500 dark:text-gray-400">{capa.action_number}</span>
                            <span className={`badge ${getPriorityBadge(capa.priority)}`}>
                                {capa.priority?.toUpperCase()}
                            </span>
                            <span className={`badge ${getStatusBadge(capa.status)}`}>
                                {capa.status?.replace('_', ' ').toUpperCase()}
                            </span>
                        </div>
                        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{capa.title}</h1>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                            {capa.owner_name && <span className="inline-flex items-center gap-1"><FileText className="w-3.5 h-3.5" /> {capa.owner_name}</span>}
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="text-right">
                            <span className="block text-xs text-gray-400">{t('dueDate')}</span>
                            <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">{capa.due_date || '—'}</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Detail Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Description */}
                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                        <FileText className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                        {t('description')}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{capa.description || '—'}</p>
                </div>

                {/* Recommendation */}
                <div className="bg-white dark:bg-slate-900 border border-gray-200 dark:border-slate-800 rounded-xl p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                        <MessageCircle className="w-4 h-4 text-blue-500" />
                        {t('recommendation')}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">{capa.recommendation || '—'}</p>
                </div>
            </div>
        </div>
    );
}

export default CapaDetailPage;