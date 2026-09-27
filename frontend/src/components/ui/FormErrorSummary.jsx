import { useI18n } from '../../context/I18nContext';

/** Humanize a validation key: `first_name` -> `First name`. */
const humanize = (key) =>
  String(key).replace(/_/g, ' ').replace(/^\w/, (char) => char.toUpperCase());

/**
 * The "these fields need attention" banner for a validated form.
 *
 * Its absence was a real defect, not a cosmetic one. Six pages ran
 * `if (hasErrors(errors)) { setFormErrors(errors); return; }` — collecting the
 * errors, storing them in this state, and then rendering nothing and saying
 * nothing. A refused submit looked like a dead button: no message, no highlight,
 * no reason given.
 *
 * It names the offending fields, because a banner saying only "some fields need
 * attention" leaves the user hunting for which. `UsersPage` avoids that by
 * rendering a `form-error` paragraph under each input, which is the better
 * treatment; these pages have no per-field markup, so naming the fields here is
 * what makes the message actionable.
 *
 * Renders nothing when there is nothing to report — which is what makes it safe to
 * place unconditionally at the top of a form, including forms whose handler never
 * sets errors.
 *
 * Note the message is English-only, matching `UsersPage`'s existing banner. Both
 * are user-facing text that the Amharic dictionary does not cover yet; they belong
 * with the wider i18n pass rather than being half-translated here.
 */
function FormErrorSummary({ errors }) {
  const { t } = useI18n();
  const entries =
    errors && typeof errors === 'object' ? Object.entries(errors) : [];
  if (entries.length === 0) return null;

  return (
    <div className="alert alert-red" role="alert">
      <span className="alert-icon">!</span>
      <div>
        <span>{t('formErrorSummary')}</span>
        <ul className="form-error-list">
          {entries.map(([field, message]) => (
            <li key={field}>
              <strong>{humanize(field)}</strong>
              {': '}
              {Array.isArray(message) ? message.join(' ') : String(message)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default FormErrorSummary;
