import json,uuid
from app.repositories import thesis_repo,report_repo,base_repo
from app.models.research_schema import ThesisPart
from app.models.schema import Document
from app.services.final_acceptance_service import accept_report
from app.services.self_match_service import reference_ids_for_work


def test_combined_acceptance_uses_internal_files_and_preserves_part_provenance(tmp_path):
    tid,_=thesis_repo.create_thesis('Safe acceptance thesis','Fixture author',created_by='employee_fixture')
    rid='combined_'+uuid.uuid4().hex
    with base_repo.get_session() as db:
        for i in range(2):
            path=tmp_path/f'chapter-{i}.txt'
            path.write_text(('تبحث هذه الدراسة مبادئ التوثيق الأكاديمي ومراجعة المصادر الأصلية ' if i==0 else 'يتناول الفصل الثاني أساليب حماية المعلومات ومناهج البحث العلمي ')+rid,encoding='utf-8')
            db.add(ThesisPart(thesis_id=tid,part_title=f'Chapter {i}',sort_order=i,file_path=str(path),original_filename=path.name,stored_filename=path.name,file_type='txt',scan_status='completed'))
    data={'is_combined_thesis':True,'is_complete_thesis':True,'thesis_id':tid}
    report_repo.save_report(report_id=rid,title='Thesis '+rid,overall_pct=0,copied_pct=0,para_pct=0,report_dict=data)
    thesis_repo.update_thesis_status(tid,status='completed',combined_report_id=rid,is_stale=0)
    results=accept_report(dict(report_repo.get_report(rid),**data),{'username':'independent_admin','role':'system_admin'})
    assert len(results)==2 and all(r['success'] for r in results)
    ids={r['id'] for r in results}
    assert reference_ids_for_work(thesis_id=tid)==ids
    with base_repo.get_session() as db:
        provenance=[json.loads(db.get(Document,i).notes) for i in ids]
        assert len({p['part_id'] for p in provenance})==2
        assert all(p['thesis_id']==tid and p['report_id']==rid for p in provenance)
    assert thesis_repo.get_thesis(tid)['review_status']=='final_accepted'
