import React, { useState, useEffect } from 'react';
import { usersApi, planningApi } from '../api';
import { Building2, Users, FolderKanban, Activity, ShieldAlert, ChevronDown, ChevronRight } from 'lucide-react';

const DIRECTORATE_COLORS = {
    IAEO: '#2563eb',
    FPA: '#10b981',
    TA: '#f59e0b',
    ITA: '#8b5cf6',
    PP: '#06b6d4',
};

const DIRECTORATE_ICONS = {
    IAEO: Building2,
    FPA: FolderKanban,
    TA: Activity,
    ITA: ShieldAlert,
    PP: Users,
};

function EEUOrgChart({ onSelectDirectorate }) {
    const [orgData, setOrgData] = useState(null);
    const [expanded, setExpanded] = useState({});
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState({});

    useEffect(() => {
        let cancelled = false;

        async function loadOrgData() {
            try {
                // Ask the API for the IAEO node directly. Scanning a page of
                // departments used to work, but the table is now 600+ units
                // deep and IAEO falls well past the first page.
                const departments = await usersApi.getDepartments({ directorate_type: 'IAEO' });
                const iaeo = departments.find(d => d.directorate_type === 'IAEO') || departments.find(d => d.code === 'IAEO');

                if (!iaeo) {
                    setOrgData(null);
                    setLoading(false);
                    return;
                }

                // Fetch directorate-specific stats
                const [universe, plans, engagements] = await Promise.all([
                    planningApi.getUniverse({ page_size: 100 }),
                    planningApi.getPlans({ page_size: 100 }),
                    planningApi.getEngagements({ page_size: 100 }),
                ]);

                const universeList = Array.isArray(universe) ? universe : (universe?.results || []);
                const plansList = Array.isArray(plans) ? plans : (plans?.results || []);
                const engagementsList = Array.isArray(engagements) ? engagements : (engagements?.results || []);

                const statsByDept = {};
                const allDepts = [iaeo, ...(iaeo.children || [])];

                allDepts.forEach(dept => {
                    const deptId = dept.id;
                    const deptUniverse = universeList.filter(u => u.directorate === deptId || u.department === deptId);
                    const deptEngagements = engagementsList.filter(e => e.directorate === deptId || e.department === deptId);
                    const deptPlans = plansList.filter(p => p.directorate === deptId);

                    const activeEngagements = deptEngagements.filter(e => ['planned', 'in_progress', 'fieldwork', 'reporting'].includes(e.status));
                    const avgRisk = deptUniverse.length > 0
                        ? deptUniverse.reduce((sum, u) => sum + (parseFloat(u.risk_score) || 0), 0) / deptUniverse.length
                        : 0;

                    statsByDept[deptId] = {
                        universeCount: deptUniverse.length,
                        engagementCount: deptEngagements.length,
                        activeEngagements: activeEngagements.length,
                        planCount: deptPlans.length,
                        avgRiskScore: Math.round(avgRisk * 10) / 10,
                        riskExposure: avgRisk >= 4.5 ? 'Critical' : avgRisk >= 3.5 ? 'High' : avgRisk >= 2.5 ? 'Medium' : 'Low',
                    };
                });

                if (!cancelled) {
                    setOrgData(iaeo);
                    setStats(statsByDept);
                    setExpanded({ [iaeo.id]: true });
                }
            } catch (err) {
                console.error('Failed to load org chart data:', err);
                if (!cancelled) {
                    setOrgData(null);
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        loadOrgData();
        return () => { cancelled = true; };
    }, []);

    if (loading) {
        return (
            <div className="org-chart-loading">
                <div className="spinner" />
                <span>Loading organizational structure...</span>
            </div>
        );
    }

    if (!orgData) {
        return (
            <div className="org-chart-empty">
                <Building2 size={32} />
                <p>EEU Internal Audit organizational structure not found. Run the seed command to initialize it.</p>
            </div>
        );
    }

    const children = orgData.children || [];

    return (
        <div className="org-chart">
            {/* ── Root Node: Internal Audit Executive Office ── */}
            <div className="org-root">
                <OrgNode
                    dept={orgData}
                    stats={stats[orgData.id]}
                    isRoot
                    expanded={!!expanded[orgData.id]}
                    onToggle={() => setExpanded(prev => ({ ...prev, [orgData.id]: !prev[orgData.id] }))}
                    onSelect={onSelectDirectorate}
                />
            </div>

            {/* ── Branching Lines ── */}
            {expanded[orgData.id] && children.length > 0 && (
                <div className="org-branches">
                    <div className="org-connector-vertical" />
                    <div className="org-connector-horizontal" />
                    <div className="org-children">
                        {children.map((child, idx) => (
                            <div key={child.id} className="org-child-column">
                                <div className="org-connector-vertical-short" />
                                <OrgNode
                                    dept={child}
                                    stats={stats[child.id]}
                                    isRoot={false}
                                    expanded={!!expanded[child.id]}
                                    onToggle={() => setExpanded(prev => ({ ...prev, [child.id]: !prev[child.id] }))}
                                    onSelect={onSelectDirectorate}
                                />
                                {child.children && child.children.length > 0 && expanded[child.id] && (
                                    <div className="org-grandchildren">
                                        {child.children.map(gc => (
                                            <OrgNode
                                                key={gc.id}
                                                dept={gc}
                                                stats={stats[gc.id]}
                                                isRoot={false}
                                                expanded={false}
                                                onToggle={() => { }}
                                                onSelect={onSelectDirectorate}
                                            />
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

function OrgNode({ dept, stats, isRoot, expanded, onToggle, onSelect }) {
    const Icon = DIRECTORATE_ICONS[dept.directorate_type] || Building2;
    const color = DIRECTORATE_COLORS[dept.directorate_type] || '#64748b';
    const isPP = dept.directorate_type === 'PP';

    return (
        <div
            className={`org-node ${isRoot ? 'org-node-root' : ''} ${isPP ? 'org-node-pp' : ''}`}
            style={{ '--node-color': color }}
            onClick={() => onSelect && onSelect(dept)}
        >
            <div className="org-node-header">
                <div className="org-node-icon" style={{ background: `${color}22`, color }}>
                    <Icon size={18} />
                </div>
                <div className="org-node-title">
                    <h4>{dept.name}</h4>
                    <span className="org-node-code">{dept.code}</span>
                </div>
                {!isRoot && dept.children && dept.children.length > 0 && (
                    <button
                        className="org-node-toggle"
                        onClick={(e) => { e.stopPropagation(); onToggle(); }}
                        aria-label="Toggle children"
                    >
                        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                )}
            </div>

            <div className="org-node-body">
                <div className="org-node-head">
                    <span className="org-node-label">Head</span>
                    <strong>{dept.head || '—'}</strong>
                </div>

                <div className="org-node-stats">
                    <div className="org-stat">
                        <Users size={13} />
                        <span>{dept.staff_count ?? 0}</span>
                        <small>Staff</small>
                    </div>
                    <div className="org-stat">
                        <FolderKanban size={13} />
                        <span>{stats?.universeCount ?? 0}</span>
                        <small>Universe</small>
                    </div>
                    <div className="org-stat">
                        <Activity size={13} />
                        <span>{stats?.activeEngagements ?? 0}</span>
                        <small>Active</small>
                    </div>
                </div>

                {stats && (
                    <div className="org-node-risk">
                        <span className="org-node-label">Risk Exposure</span>
                        <span className={`risk-badge risk-${(stats.riskExposure || 'low').toLowerCase()}`}>
                            {stats.riskExposure || 'Low'}
                        </span>
                        <span className="org-node-risk-score">Score: {stats.avgRiskScore ?? 0}</span>
                    </div>
                )}

                {isPP && (
                    <div className="org-node-pp-badge">
                        <ShieldAlert size={12} />
                        Consolidated Oversight
                    </div>
                )}
            </div>
        </div>
    );
}

export default EEUOrgChart;