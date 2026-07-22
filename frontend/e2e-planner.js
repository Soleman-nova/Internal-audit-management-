import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:8000/api';

async function runEndToEndTest() {
  console.log('--- Starting End-to-End Audit Planner Test ---');

  try {
    // 1. Login
    console.log('1. Logging in as Audit Manager...');
    const loginRes = await axios.post(`${API_BASE_URL}/auth/login/`, {
      email: 'manager@eeu.com',
      password: 'user123'
    });
    const token = loginRes.data.access;
    console.log('   ✅ Login successful.');

    const apiClient = axios.create({
      baseURL: API_BASE_URL,
      headers: { Authorization: `Bearer ${token}` }
    });

    // 2. Fetch Departments
    console.log('\n2. Fetching Departments...');
    const depRes = await apiClient.get('/auth/departments/');
    const departments = depRes.data.results;
    if (!departments || departments.length === 0) {
      throw new Error('No departments found. Seed data might be missing.');
    }
    const targetDept = departments[0];
    console.log(`   ✅ Found department: ${targetDept.name}`);

    // 3. Create Audit Universe Entity
    console.log('\n3. Creating new Audit Universe Entity...');
    const univCode = `E2E-UNIV-${Date.now().toString().slice(-4)}`;
    const univRes = await apiClient.post('/planning/universe/', {
      name: 'E2E Testing Node',
      code: univCode,
      category: 'system',
      risk_score: 4.5,
      audit_frequency: 'Annually',
      department: targetDept.id
    });
    const universeId = univRes.data.id;
    console.log(`   ✅ Universe Entity created with ID: ${universeId} (${univCode})`);

    // 4. Create Annual Audit Plan
    console.log('\n4. Creating Annual Audit Plan...');
    const planRes = await apiClient.post('/planning/plans/', {
      title: `E2E Automated Plan ${new Date().getFullYear()}`,
      year: new Date().getFullYear(),
      total_budget_days: 120,
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      description: 'Automatically generated plan for E2E testing.'
    });
    const planId = planRes.data.id;
    console.log(`   ✅ Annual Plan created with ID: ${planId}`);

    // 5. Schedule an Audit Engagement
    console.log('\n5. Scheduling Audit Engagement...');
    const engRes = await apiClient.post('/planning/engagements/', {
      title: 'E2E Validation Audit',
      plan: planId,
      audit_universe: universeId,
      department: targetDept.id,
      engagement_type: 'it',
      risk_level: 'high',
      planned_start: '2026-06-01',
      planned_end: '2026-06-30'
    });
    console.log(`   ✅ Audit Engagement created: ${engRes.data.engagement_number}`);

    // 6. Submit the Plan for Approval
    console.log('\n6. Submitting Plan for Approval...');
    await apiClient.post(`/planning/plans/${planId}/submit/`);
    
    // Verify it was submitted
    const checkPlanRes = await apiClient.get(`/planning/plans/${planId}/`);
    if (checkPlanRes.data.status === 'submitted') {
      console.log(`   ✅ Plan successfully submitted! Status: ${checkPlanRes.data.status}`);
    } else {
      console.log(`   ❌ Plan submission failed. Status: ${checkPlanRes.data.status}`);
    }

    console.log('\n🎉 --- End-to-End Test Completed Successfully! --- 🎉');
  } catch (error) {
    console.error('\n❌ E2E Test Failed:');
    if (error.response) {
      console.error(error.response.data);
    } else {
      console.error(error.message);
    }
    process.exit(1);
  }
}

runEndToEndTest();
