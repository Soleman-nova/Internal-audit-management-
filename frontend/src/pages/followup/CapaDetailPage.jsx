import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { capaApi } from '../../api';
import { useToast } from '../../context/ToastContext';
import { useI18n } from '../../context/I18nContext';
import Spinner from '../../components/ui/Spinner';
import { ArrowLeft, AlertCircle, MessageCircle, FileText } from 'lucide-react';

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
                        </div>
                        <h2>{capa.title}</h2>
                        {capa.owner_name && (
                            <p className="text-sm text-secondary mt-1 inline-flex items-center gap-1">
                                <FileText size={14} /> {capa.owner_name}
                            </p>
                        )}
                    </div>
                    <div className="text-right">
                        <span className="block text-xs text-muted">{t('dueDate')}</span>
                        <strong className="text-sm">{capa.due_date || '—'}</strong>
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
                    <p className="text-sm text-secondary">{capa.description || '—'}</p>
                </div>

                {/* Recommendation */}
                <div className="card">
                    <div className="card-header">
                        <h3 className="flex items-center gap-2">
                            <MessageCircle size={16} className="text-accent" />
                            {t('recommendation')}
                        </h3>
                    </div>
                    <p className="text-sm text-secondary">{capa.recommendation || '—'}</p>
                </div>
            </div>
        </div>
    );
}

export default CapaDetailPage;