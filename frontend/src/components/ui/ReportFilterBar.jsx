import React, { useState, useEffect } from 'react';
import {
  Search, Calendar, Building2, User, FileText, CheckCircle2,
  X, Filter, RotateCcw, ChevronDown, ChevronUp, FileSpreadsheet
} from 'lucide-react';
import { useI18n } from '../../context/I18nContext';

const DIRECTORATE_OPTIONS = [
  { value: '', labelEn: 'All Directorates', labelAm: 'ሁሉም ዳይሬክቶሬቶች' },
  { value: 'FPA', labelEn: 'Financial & Performance Audit', labelAm: 'የፋይናንስና የአፈጻጸም ኦዲት' },
  { value: 'TA', labelEn: 'Technical Audit', labelAm: 'የቴክኒክ ኦዲት' },
  { value: 'ITA', labelEn: 'Information Technology Audit', labelAm: 'የኢንፎርሜሽን ቴክኖሎጂ ኦዲት' },
  { value: 'PP', labelEn: 'Planning & Performance', labelAm: 'የዕቅድና አፈጻጸም' },
];

const STATUS_OPTIONS = [
  { value: 'ready', label: 'Ready', color: 'badge-success' },
  { value: 'generating', label: 'Generating', color: 'badge-warning' },
  { value: 'failed', label: 'Failed', color: 'badge-danger' },
];

const FORMAT_OPTIONS = [
  { value: 'pdf', label: 'PDF' },
  { value: 'excel', label: 'Excel' },
  { value: 'word', label: 'Word' },
];

export function ReportFilterBar({
  filters,
  onChange,
  onReset,
  templates = [],
  auditors = [],
  directorates = [],
}) {
  const { t, lang } = useI18n();
  const [expanded, setExpanded] = useState(false);

  // Count how many non-default filters are active
  const activeFilterCount = Object.entries(filters).filter(([key, val]) => {
    if (!val) return false;
    if (Array.isArray(val) && val.length === 0) return false;
    return true;
  }).length;

  const handleInputChange = (field, value) => {
    onChange({
      ...filters,
      [field]: value,
    });
  };

  const handleStatusToggle = (status) => {
    const currentStatuses = filters.status ? filters.status.split(',').filter(Boolean) : [];
    const exists = currentStatuses.includes(status);
    let updated;
    if (exists) {
      updated = currentStatuses.filter(s => s !== status);
    } else {
      updated = [...currentStatuses, status];
    }
    handleInputChange('status', updated.join(','));
  };

  const handleFormatToggle = (fmt) => {
    const currentFormats = filters.format ? filters.format.split(',').filter(Boolean) : [];
    const exists = currentFormats.includes(fmt);
    let updated;
    if (exists) {
      updated = currentFormats.filter(f => f !== fmt);
    } else {
      updated = [...currentFormats, fmt];
    }
    handleInputChange('format', updated.join(','));
  };

  const selectedStatuses = filters.status ? filters.status.split(',').filter(Boolean) : [];
  const selectedFormats = filters.format ? filters.format.split(',').filter(Boolean) : [];

  return (
    <div className="report-filter-panel card">
      {/* ── Top Bar: Search keyword + Quick toggles + Expand button ── */}
      <div className="report-filter-header flex flex-wrap items-center justify-between gap-3 p-3">
        <div className="flex items-center gap-2 flex-1 min-w-[240px]">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              className="form-control report-search-input text-sm"
              aria-label={t('searchReportsPlaceholder') || 'Search reports by title, engagement number, or template...'}
              placeholder={t('searchReportsPlaceholder') || 'Search reports by title, engagement number, or template...'}
              value={filters.search || ''}
              onChange={(e) => handleInputChange('search', e.target.value)}
            />
            {filters.search && (
              <button
                type="button"
                className="report-search-clear absolute right-2 top-1/2 -translate-y-1/2"
                onClick={() => handleInputChange('search', '')}
                aria-label={t('layoutClear') || 'Clear search'}
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Quick Directorate Filter */}
          <select
            className="form-control text-sm"
            style={{ maxWidth: '200px' }}
            value={filters.directorate || ''}
            onChange={(e) => handleInputChange('directorate', e.target.value)}
          >
            {DIRECTORATE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {lang === 'am' ? opt.labelAm : opt.labelEn}
              </option>
            ))}
          </select>

          {/* Expand Advanced Filters */}
          <button
            type="button"
            className={`btn btn-sm ${activeFilterCount > 0 ? 'btn-primary' : 'btn-outline'} flex items-center gap-1.5`}
            onClick={() => setExpanded(!expanded)}
          >
            <Filter size={14} />
            <span>{t('filters') || 'Filters'}</span>
            {activeFilterCount > 0 && (
              <span className="badge badge-light">
                {activeFilterCount}
              </span>
            )}
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {activeFilterCount > 0 && (
            <button
              type="button"
              className="btn btn-outline btn-sm report-reset-btn flex items-center gap-1"
              onClick={onReset}
              title={t('resetFilters') || 'Reset all filters'}
            >
              <RotateCcw size={13} />
              <span className="hidden sm:inline">{t('reset') || 'Reset'}</span>
            </button>
          )}
        </div>
      </div>

      {/* ── Collapsible Advanced Filter Drawer ── */}
      {expanded && (
        <div className="report-filter-body p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            {/* Date Range: From Date */}
            <div className="form-group mb-0">
              <label className="form-label text-xs font-semibold flex items-center gap-1.5">
                <Calendar size={13} /> {t('dateFrom') || 'Date From'}
              </label>
              <input
                type="date"
                className="form-control text-sm"
                value={filters.date_from || ''}
                onChange={(e) => handleInputChange('date_from', e.target.value)}
              />
            </div>

            {/* Date Range: To Date */}
            <div className="form-group mb-0">
              <label className="form-label text-xs font-semibold flex items-center gap-1.5">
                <Calendar size={13} /> {t('dateTo') || 'Date To'}
              </label>
              <input
                type="date"
                className="form-control text-sm"
                value={filters.date_to || ''}
                onChange={(e) => handleInputChange('date_to', e.target.value)}
              />
            </div>

            {/* Auditor Filter */}
            <div className="form-group mb-0">
              <label className="form-label text-xs font-semibold flex items-center gap-1.5">
                <User size={13} /> {t('auditor') || 'Auditor / Generated By'}
              </label>
              <select
                className="form-control text-sm"
                value={filters.auditor || ''}
                onChange={(e) => handleInputChange('auditor', e.target.value)}
              >
                <option value="">{t('allAuditors') || 'All Auditors'}</option>
                {auditors.map((aud) => (
                  <option key={aud.id} value={aud.id}>
                    {aud.full_name || `${aud.first_name || ''} ${aud.last_name || ''}`.trim() || aud.username}
                  </option>
                ))}
              </select>
            </div>

            {/* Report Template Filter */}
            <div className="form-group mb-0">
              <label className="form-label text-xs font-semibold flex items-center gap-1.5">
                <FileText size={13} /> {t('reportTemplate') || 'Report Template'}
              </label>
              <select
                className="form-control text-sm"
                value={filters.template || ''}
                onChange={(e) => handleInputChange('template', e.target.value)}
              >
                <option value="">{t('allTemplates') || 'All Templates'}</option>
                {templates.map((tpl) => (
                  <option key={tpl.id} value={tpl.id}>
                    {tpl.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Status & Format Chips Row */}
          <div className="report-filter-chips flex flex-wrap items-center justify-between gap-4 mt-4 pt-3">
            {/* Status Pills */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-muted">{t('status') || 'Status'}:</span>
              <div className="flex items-center gap-1.5">
                {STATUS_OPTIONS.map((st) => {
                  const isChecked = selectedStatuses.includes(st.value);
                  return (
                    <button
                      key={st.value}
                      type="button"
                      className={`btn btn-xs ${
                        isChecked ? 'btn-primary' : 'btn-outline opacity-80 hover:opacity-100'
                      }`}
                      onClick={() => handleStatusToggle(st.value)}
                    >
                      {st.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Format Pills */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-muted">{t('format') || 'Format'}:</span>
              <div className="flex items-center gap-1.5">
                {FORMAT_OPTIONS.map((fmt) => {
                  const isChecked = selectedFormats.includes(fmt.value);
                  return (
                    <button
                      key={fmt.value}
                      type="button"
                      className={`btn btn-xs ${
                        isChecked ? 'btn-accent' : 'btn-outline opacity-80 hover:opacity-100'
                      }`}
                      onClick={() => handleFormatToggle(fmt.value)}
                    >
                      {fmt.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ReportFilterBar;
