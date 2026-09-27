import { useState } from 'react';
import { planningApi } from '../../../api';
import { useToast } from '../../../context/ToastContext';
import { useI18n } from '../../../context/I18nContext';
import useAsyncData from '../../../hooks/useAsyncData';
import Modal from '../../../components/ui/Modal';
import FormErrorSummary from '../../../components/ui/FormErrorSummary';
import { emptyTeamMember } from '../planningForms';

/**
 * The Manage Team modal: the engagement's current roster and the form that adds
 * to it.
 *
 * It owns both the roster fetch and the add-member form. The fetch lives here
 * rather than on the page because it is the modal that needs it, and it is keyed
 * on the engagement it was given — the page passes an **id** and the row is
 * resolved against the current list, never stored.
 *
 * Props:
 *   isOpen        whether the modal is showing (the page requires a selected
 *                 engagement for this to be true)
 *   onClose       close it
 *   engagementId  the engagement whose roster is shown and added to
 *   engagement    that row, for the title; null while the list has not resolved
 *   users         every user, for the member picker
 */
function TeamModal({ isOpen, onClose, engagementId, engagement, users }) {
  const toast = useToast();
  const { t } = useI18n();
  const [teamMember, setTeamMember] = useState(emptyTeamMember);
  // Never written: adding a member has no client-side validation, and a refusal
  // is reported by the toast. The banner slot is kept so this form has the same
  // shape as every other one — and so a failure here can be reported the same way.
  const [formErrors] = useState({});

  // Team list for the Manage Team modal. Keyed on the selected engagement, and
  // `enabled` is load-bearing rather than a nicety: the id starts null, and
  // without it the first render would request the team of engagement 0 — an
  // unfiltered call that returns some other engagement's roster.
  //
  // Opening the modal is what triggers the load: the id it is handed is
  // non-null by then and the hook — which is disabled while it is null — runs.
  // Closing unmounts this component, so re-opening the same engagement fetches
  // again, which is what the old per-open request did.
  const {
    data: engagementTeamData,
    reload: reloadEngagementTeam,
  } = useAsyncData(
    async () => {
      const res = await planningApi.getEngagement(engagementId);
      return res.team_members || [];
    },
    [engagementId],
    {
      enabled: Boolean(engagementId),
      onError: () => toast.error(t('teamLoadFailed')),
    },
  );

  const engagementTeam = engagementTeamData ?? [];

  const handleAddTeamMember = async (e) => {
    e.preventDefault();
    try {
      await planningApi.addTeamMember(engagementId, teamMember);
      toast.success(t('teamMemberAssigned'));
      // Refresh team through the hook, so the response is versioned like any
      // other load rather than assigned blind.
      reloadEngagementTeam();
      setTeamMember(emptyTeamMember);
    } catch (err) {
      const msg = typeof err.response?.data === 'object' ? JSON.stringify(err.response.data) : t('teamMemberFailed');
      toast.error(msg);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={engagement ? t('manageTeamTitle', engagement.title) : t('manageTeam')}
      size="xl"
      footer={(
        <>
          <button type="button" className="btn btn-outline" onClick={onClose}>{t('close')}</button>
          <button type="submit" form="team-member-form" className="btn btn-primary">{t('addMember')}</button>
        </>
      )}
    >
      {/* Existing team */}
      {engagementTeam.length > 0 && (
        <div className="mb-4">
          <h4 className="mb-2">{t('currentTeamMembers')}</h4>
          {/* .table has no min-width of its own, so without this wrapper the
              columns compress instead of scrolling on a narrow screen. */}
          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('name')}</th>
                  <th>{t('role')}</th>
                  <th>{t('allocatedDays')}</th>
                </tr>
              </thead>
              <tbody>
                {engagementTeam.map(tm => (
                  <tr key={tm.id}>
                    <td>{tm.user_details?.full_name || tm.user_details?.employee_id}</td>
                    <td><span className="badge badge-outline">{tm.role?.toUpperCase()}</span></td>
                    <td>{tm.allocated_days} {t('days')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Add new member form */}
      <form id="team-member-form" onSubmit={handleAddTeamMember}>
        <FormErrorSummary errors={formErrors} />
        <div className="form-section-divider"><span>{t('addTeamMember')}</span></div>
        <div className="form-group-row">
          <div className="form-group">
            <label className="form-label" htmlFor="team_user">{t('user')}</label>
            <select id="team_user" className="form-control" value={teamMember.user}
              onChange={(e) => setTeamMember({ ...teamMember, user: e.target.value })} required>
              <option value="">{t('selectUser')}</option>
              {users.map(u => (
                <option key={u.id} value={u.id}>{u.full_name || `${u.first_name} ${u.last_name}`} ({u.role})</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="team_role">{t('roleInEngagement')}</label>
            <select id="team_role" className="form-control" value={teamMember.role}
              onChange={(e) => setTeamMember({ ...teamMember, role: e.target.value })}>
              <option value="lead">{t('leadAuditor')}</option>
              <option value="member">{t('teamRoleMember')}</option>
              <option value="supervisor">{t('supervisor')}</option>
              <option value="specialist">{t('teamRoleSpecialist')}</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="team_allocated_days">{t('allocatedDays')}</label>
            <input id="team_allocated_days" type="number" min="0" className="form-control"
              value={teamMember.allocated_days}
              onChange={(e) => setTeamMember({ ...teamMember, allocated_days: parseInt(e.target.value) || 0 })} />
          </div>
        </div>
      </form>
    </Modal>
  );
}

export default TeamModal;
