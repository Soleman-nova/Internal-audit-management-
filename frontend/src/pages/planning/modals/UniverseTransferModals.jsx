import { useState } from 'react';
import { planningApi } from '../../../api';
import { useToast } from '../../../context/ToastContext';
import { useI18n } from '../../../context/I18nContext';
import Modal from '../../../components/ui/Modal';
import FormErrorSummary from '../../../components/ui/FormErrorSummary';
import { Download } from 'lucide-react';

/**
 * Bulk import and export of the Audit Universe (Excel/CSV).
 *
 * Both modals are rendered by the page unconditionally with an `isOpen` prop.
 * The import modal owns its file picker, its busy flag and its result panel, all
 * of which the page used to reset by hand from its open/close handlers; because
 * `Modal` renders its children only while open, they are now discarded on close
 * by simply unmounting.
 */

/**
 * Export the full universe as a spreadsheet. No form and no state: the two
 * buttons are the whole interface.
 *
 * Props:
 *   isOpen    whether the modal is showing
 *   onClose   close it, including after a successful download
 */
export function UniverseExportModal({ isOpen, onClose }) {
  const toast = useToast();
  const { t } = useI18n();

  const handleExportUniverse = async (format) => {
    try {
      await planningApi.exportUniverse(format);
      toast.success(format === 'csv' ? t('universeExportedCsv') : t('universeExportedExcel'));
      onClose();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : t('exportFailed');
      toast.error(msg);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t('universeExportTitle')}
      subtitle={t('universeExportSubtitle')}
    >
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
        {t('universeExportBody')}
      </p>
      <div className="flex flex-col gap-2">
        <button className="btn btn-outline flex items-center gap-2" onClick={() => handleExportUniverse('xlsx')}>
          <Download size={16} /> {t('excelXlsx')}
        </button>
        <button className="btn btn-outline flex items-center gap-2" onClick={() => handleExportUniverse('csv')}>
          <Download size={16} /> {t('csv')}
        </button>
      </div>
    </Modal>
  );
}

/**
 * Import the universe from an .xlsx or .csv file, then show what the server did
 * with it. The result panel replaces the picker on success, so the modal stays
 * open until the user closes it.
 *
 * Props:
 *   isOpen      whether the modal is showing
 *   onClose     close it (Cancel, the X, or Close on the result panel)
 *   onImported  called after a successful import so the page can refetch the
 *               universe tab and the reference catalogs
 */
export function UniverseImportModal({ isOpen, onClose, onImported }) {
  const toast = useToast();
  const { t } = useI18n();
  const [importBusy, setImportBusy] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importResult, setImportResult] = useState(null);
  // Never written: a refused import is reported by a toast and by the result
  // panel's error list, but the banner slot is kept so this form matches every
  // other form's shape.
  const [formErrors] = useState({});

  const handleImportUniverse = async (e) => {
    e.preventDefault();
    if (!importFile) {
      toast.warning(t('importChooseFile'));
      return;
    }
    setImportBusy(true);
    setImportResult(null);
    try {
      const result = await planningApi.importUniverse(importFile);
      setImportResult(result);
      if (result.created || result.updated) {
        toast.success(t('importComplete', result.created, result.updated));
      } else {
        toast.info(t('importNoChanges'));
      }
      if (result.errors?.length) {
        toast.error(t('importRowErrors', result.errors.length));
      }
      onImported();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : t('importFailed');
      toast.error(msg);
      setImportResult({ created: 0, updated: 0, errors: [{ row: null, message: msg }] });
    } finally {
      setImportBusy(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t('universeImportTitle')}
      subtitle={t('universeImportSubtitle')}
      footer={
        importResult ? (
          <button type="button" className="btn btn-primary" onClick={onClose}>
            {t('close')}
          </button>
        ) : (
          <>
            <button type="button" className="btn btn-outline" onClick={onClose}>
              {t('cancel')}
            </button>
            <button
              type="submit"
              form="universe-import-form"
              className="btn btn-primary flex items-center gap-2"
              disabled={importBusy}
            >
              {importBusy ? t('importing') : t('import')}
            </button>
          </>
        )
      }
    >
      <form id="universe-import-form" onSubmit={handleImportUniverse}>
        <FormErrorSummary errors={formErrors} />
        {importResult ? (
          <div className="space-y-3">
            <div className="flex gap-2">
              <span className="badge badge-success">{t('importCreated', importResult.created ?? 0)}</span>
              <span className="badge badge-info">{t('importUpdated', importResult.updated ?? 0)}</span>
              <span className="badge badge-warning">{t('importErrorCount', importResult.errors?.length ?? 0)}</span>
            </div>
            {importResult.errors?.length > 0 && (
              <div className="max-h-64 overflow-auto border border-rose-200 dark:border-rose-900 rounded-lg p-3 text-xs">
                <p className="font-semibold mb-2 text-rose-700 dark:text-rose-400">
                  {t('importRowsFailed')}
                </p>
                {importResult.errors.slice(0, 20).map((err, i) => (
                  <p key={i} className="mb-1 text-gray-700 dark:text-gray-300">
                    {err.row != null ? <span className="font-semibold">{t('importRowLabel', err.row)}{' '}</span> : null}
                    {err.message}
                  </p>
                ))}
                {importResult.errors.length > 20 && (
                  <p className="text-gray-500 dark:text-gray-400">
                    {t('importMoreRows', importResult.errors.length - 20)}
                  </p>
                )}
              </div>
            )}
          </div>
        ) : (
          <div>
            <p className="mb-3 text-sm text-gray-600 dark:text-gray-400">
              {t('importHintIntro')}{' '}
              <strong>{t('code')}</strong>
              {t('importHintAfterCode')}{' '}
              <strong>{t('export')}</strong>{' '}
              {t('importHintAfterExport')}
            </p>
            <label className="form-label" htmlFor="universe_import_file">{t('importSpreadsheetFile')}</label>
            <input
              id="universe_import_file"
              type="file"
              accept=".xlsx,.csv"
              className="form-control"
              onChange={(e) => setImportFile(e.target.files?.[0] || null)}
            />
            {importBusy && <div className="loading-spinner mt-4" />}
          </div>
        )}
      </form>
    </Modal>
  );
}
