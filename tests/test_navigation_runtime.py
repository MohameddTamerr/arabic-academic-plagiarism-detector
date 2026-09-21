"""Navigation and safe-user API regression gates, using only isolated test data."""
import json
import re
import shutil
import subprocess
from pathlib import Path
import uuid

import pytest
from app import create_app
from app.models.schema import User
from app.repositories.base_repo import get_session

ROOT = Path(__file__).resolve().parents[1]


def test_navigation_controller_executes_one_view_at_a_time(tmp_path):
    node = shutil.which('node')
    assert node, 'Node is required to execute the navigation regression test'
    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    script = re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>', html)
    # Parse every inline script; execute the actual controller with a minimal DOM.
    start = html.index("        let activeView = 'dashboard';")
    end = html.index('        // ─── Global Auth', start)
    controller = html[start:end]
    roles = html[html.index('        function normalizeUserRole('):html.index('        function updateUserUI(')]
    test_js = r'''
const vm = require('node:vm'), assert = require('node:assert/strict');
const input = JSON.parse(require('node:fs').readFileSync(process.argv[2], 'utf8'));
for (const s of input.scripts) new vm.Script(s);
const names = ['dashboard','upload','reports','theses','users','settings','help','thesis-detail','combined-report','audit'];
function element(name, nav=false) {
  const classes = new Set();
  return {id:'view-'+name, dataset:{view:name}, hidden:false, style:{removeProperty(){}},
    classList:{toggle(c,on){on?classes.add(c):classes.delete(c)},contains(c){return classes.has(c)}},
    setAttribute(){},removeAttribute(){}};
}
const views = names.map(n=>element(n)), navs = names.slice(0,7).map(n=>element(n,true));
const ctx = { currentUser:{role:'system_admin'}, sessionStorage:{setItem(){}},
 document:{getElementById:id=>views.find(v=>v.id===id),querySelector:()=>({scrollTop:99}),
 querySelectorAll:s=>s==='.view-section'?views:navs}};
for(const name of ['loadReportList','loadInitialReviewsQueue','loadPreliminaryPapers','loadRejectedPapers',
 'loadDatabasePapers','loadDashboardStats','loadUsersList','loadUserStats','loadThesesList','loadAuditLogs',
 'loadSystemHealth','startSystemHealthTimer','stopSystemHealthTimer','loadBackupsList',
 'loadSystemSettings','loadSystemDiagnostics']) ctx[name]=()=>{};
vm.createContext(ctx); vm.runInContext(input.roles+input.controller,ctx);
for (const name of names.slice(0,7)) {
 ctx.switchView(name);
 assert.deepEqual(views.filter(v=>!v.hidden).map(v=>v.id),['view-'+name]);
 assert.equal(navs.filter(v=>v.classList.contains('active')).length,1);
}
ctx.switchView('thesis-detail'); assert.equal(views.filter(v=>!v.hidden)[0].id,'view-thesis-detail');
ctx.currentUser.role='employee';
for(const name of ['users','settings','audit']) {
 ctx.switchView(name); assert.deepEqual(views.filter(v=>!v.hidden).map(v=>v.id),['view-dashboard']);
}
console.log('navigation controller passed');
'''
    js = tmp_path / 'navigation.cjs'
    payload = tmp_path / 'navigation.json'
    js.write_text(test_js, encoding='utf-8')
    payload.write_text(json.dumps({'scripts': script, 'controller': controller, 'roles': roles}), encoding='utf-8')
    result = subprocess.run([node, str(js), str(payload)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '.view-section:not(.active), .view-section[hidden]' in html
    assert "el.hidden = !selected;" in controller


@pytest.mark.parametrize('role', ['system_admin', 'employee'])
def test_existing_user_api_count_and_permissions(role):
    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    name = 'navigation_' + uuid.uuid4().hex
    with get_session() as db:
        user = User(username=name, full_name='Navigation Fixture', role=role,
                    password_hash='test-only-unused', is_active=1, session_version=1)
        db.add(user)
        db.flush()
        user_id = user.id
        total = db.query(User).count()
    with client.session_transaction() as session:
        session.update(user_id=user_id, username=name, role=role, session_version=1)
    response = client.get('/api/users?q=' + name)
    if role == 'employee':
        assert response.status_code == 403
        assert client.get('/api/users/stats').status_code == 403
        return
    assert response.status_code == 200
    data = response.get_json()
    assert data['total_items'] == 1
    user = data['users'][0]
    assert user['id'] == user_id and user['role'] == 'system_admin'
    assert {'id','username','full_name','role','is_active','department','recovery_configured'} <= user.keys()
    assert not {'password_hash','recovery_secret','qr_payload','recovery_pin','secret','pin'} & user.keys()
    assert client.get('/api/users/stats').get_json()['total_users'] == total
