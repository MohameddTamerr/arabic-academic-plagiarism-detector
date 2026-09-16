"""
Tests for Multi-Part Thesis Management, Atomic Reference Numbers,
Parts Ordering, Reordering, and Detach.
"""
import io
import pytest
from app import create_app
from app.models.schema import User
from app.models.research_schema import Thesis, ThesisPart, generate_thesis_reference
from app.repositories.base_repo import get_session as get_db_session


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def test_atomic_thesis_reference_format():
    """Verify reference format is strictly THS-YYYY-XXXXXX."""
    with get_db_session() as session:
        ref = generate_thesis_reference(session)
        assert ref.startswith('THS-')
        parts = ref.split('-')
        assert len(parts) == 3
        assert len(parts[1]) == 4  # Year
        assert len(parts[2]) == 6  # 6-digit sequence


def test_thesis_crud_workflow(client):
    """Test creating a thesis, adding parts, reordering, and detaching."""
    with get_db_session() as session:
        admin = session.query(User).filter(User.role.in_(['admin', 'system_admin'])).first()
        admin_id = admin.id if admin else 1

    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = 'admin'
        sess['username'] = 'admin'

    # 1. Create new thesis with initial parts
    file_content_1 = b"Sample text for thesis chapter 1: Introduction and Literature Review."
    file_content_2 = b"Sample text for thesis chapter 2: Methodology and Comparative Legal Framework."

    res = client.post(
        '/api/thesis',
        data={
            'title': 'أثر الذكاء الاصطناعي في العدالة الجنائية',
            'author': 'أحمد إبراهيم الشناوي',
            'degree_type': 'phd',
            'department': 'العلوم الجنائية',
            'academic_year': '2026/2025',
            'files[]': [
                (io.BytesIO(file_content_1), 'chapter1.txt'),
                (io.BytesIO(file_content_2), 'chapter2.txt')
            ],
            'labels[]': [
                'الفصل الأول: المقدمة',
                'الفصل الثاني: المنهجية'
            ],
            'orders[]': ['1', '2']
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 201
    data = res.get_json()
    assert data['success'] is True
    thesis_id = data['thesis_id']
    assert data['reference_number'].startswith('THS-')

    # 2. Add Part 3
    file_content_3 = b"Sample text for thesis chapter 3: Findings and Conclusion."
    res = client.post(
        f'/api/thesis/{thesis_id}/parts',
        data={
            'part_label': 'الفصل الثالث: النتائج والتوصيات',
            'order_index': '3',
            'file': (io.BytesIO(file_content_3), 'chapter3.txt')
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 201
    part3_id = res.get_json()['part_id']

    # 3. Duplicate Part Check / Warning
    res = client.post(
        f'/api/thesis/{thesis_id}/parts',
        data={
            'part_label': 'نسخة مكررة من الفصل الأول',
            'order_index': '4',
            'file': (io.BytesIO(file_content_1), 'chapter1_copy.txt')
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 409  # Conflict on duplicate hash

    # 4. Fetch Thesis Details
    res = client.get(f'/api/thesis/{thesis_id}')
    assert res.status_code == 200
    t_data = res.get_json()
    assert len(t_data['parts']) >= 3

    # 5. Reorder Parts
    part_ids = [p['id'] for p in t_data['parts']]
    res = client.post(f'/api/thesis/{thesis_id}/parts/reorder', json={
        'part_orders': [
            {'id': part_ids[0], 'order_index': 3, 'part_label': 'الفصل الأول المنقول للآخر'},
            {'id': part_ids[1], 'order_index': 1, 'part_label': 'الفصل الثاني كأول'},
            {'id': part_ids[2], 'order_index': 2, 'part_label': 'الفصل الثالث كأوسط'}
        ]
    })
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    # 6. Detach Part 3
    res = client.delete(f'/api/thesis/{thesis_id}/parts/{part3_id}')
    assert res.status_code == 200
    assert res.get_json()['success'] is True

    # Verify remaining count decreased by 1
    res = client.get(f'/api/thesis/{thesis_id}')
    assert res.status_code == 200
    assert len(res.get_json()['parts']) == len(t_data['parts']) - 1
