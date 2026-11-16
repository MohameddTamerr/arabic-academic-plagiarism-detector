"""Opt-in isolated Flask resource experiment; synthetic documents, no accuracy claims."""
import gc
import io
import json
import os
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('RUN_STAGE8I') != '1', reason='opt-in real-model resource benchmark')


def test_isolated_flask_upload_with_sequential_research_ai(monkeypatch):
    import psutil
    import fitz
    from app import create_app
    from app.routes import scan_routes
    research_enabled=os.environ.get('STAGE8L_WORKFLOW','research')=='research'
    if research_enabled:
        from tools.stage8h_runtime import verify_package
    root = Path(__file__).resolve().parents[1]
    profiling = os.environ.get('STAGE8J_PROFILE') == '1'
    scratch = root/os.environ.get('STAGE8J_OUTPUT_DIR', 'scratch/stage8j' if profiling else 'scratch/stage8i')
    scratch.mkdir(parents=True,exist_ok=True)
    proc=psutil.Process()
    stage=['startup']; stop=threading.Event(); measurements={}
    def snap():
        rss=private=0
        for process in [proc]+proc.children(recursive=True):
            try:
                m=process.memory_info(); rss+=m.rss; private+=getattr(m,'private',0)
            except psutil.Error: pass
        entry=measurements.setdefault(stage[0], {'peak_tree_rss':0,'peak_tree_private_bytes':0,'peak_system_used':0})
        entry['peak_tree_rss']=max(entry['peak_tree_rss'],rss)
        entry['peak_tree_private_bytes']=max(entry['peak_tree_private_bytes'],private)
        entry['peak_system_used']=max(entry['peak_system_used'],psutil.virtual_memory().used)
    def watch():
        while not stop.wait(float(os.environ.get('BENCH_SAMPLE_SECONDS','.02'))): snap()
    thread=threading.Thread(target=watch,daemon=True);thread.start()
    started=time.perf_counter(); cpu0=sum(proc.cpu_times()[:2]); available=psutil.virtual_memory().available
    app=create_app(); app.config['TESTING']=True
    startup=time.perf_counter()-started; snap()
    baseline_rss=proc.memory_info().rss
    original_extract=scan_routes.extract_document_pages
    original_analyze=scan_routes.analyze_academic_document
    original_settings=scan_routes.get_current_settings
    model=[None]; tokenizer=[None]; extracted=[0]; runs=[]; phases={}
    corpus_import_seconds=0.0
    if profiling and os.environ.get('STAGE8J_CORPUS') == 'populated':
        from app.services.paper_service import import_reference_paper
        from plagiarism_detector.reporting.report_builder import invalidate_pipeline_index
        corpus_start=time.perf_counter()
        base='تتناول هذه الدراسة تحليل البيانات وتوثيق مصادر المعلومات ومراجعة النتائج باستخدام منهج واضح قابل للتحقق '
        for number in range(20):
            text=base if number==0 else f'تبحث الدراسة رقم {number} في موضوع مستقل عن إدارة الموارد وتحليل السياسات ومراجعة الشواهد والمصادر العلمية. '
            imported=import_reference_paper(title=f'Synthetic source {number}',author='synthetic fixture',raw_text=text*10,ownership_note='Generated test fixture; no real author label')
            assert imported.get('success'), imported
        invalidate_pipeline_index()
        corpus_import_seconds=time.perf_counter()-corpus_start
    if profiling:
        from app.repositories import report_repo
        from plagiarism_detector.reporting import report_builder
        def instrument(owner,name,key):
            original=getattr(owner,name)
            def timed(*args,**kwargs):
                begin=time.perf_counter()
                try:return original(*args,**kwargs)
                finally:
                    phases[key]=phases.get(key,0.0)+time.perf_counter()-begin
                    phases[key+'_calls']=phases.get(key+'_calls',0)+1
            monkeypatch.setattr(owner,name,timed)
        for name in ('get_pipeline_index','alignment_evidence','match_exact_or_near_copy','match_lexical_paraphrase'):
            instrument(report_builder,name,name+'_seconds')
        for name in ('retrieve_candidates','retrieve_candidates_for_shingles'):
            instrument(report_builder.CandidateRetriever,name,name+'_seconds')
        save_original=report_repo.save_report
        def timed_save(*args,**kwargs):
            begin=time.perf_counter()
            try:return save_original(*args,**kwargs)
            finally:phases['report_persistence_seconds']=time.perf_counter()-begin
        monkeypatch.setattr(report_repo,'save_report',timed_save)
    def extract(*args,**kwargs):
        stage[0]='extraction'; begin=time.perf_counter(); extracted[0]+=1
        try:
            pages=original_extract(*args,**kwargs)
            phases['extracted_words']=sum(len(p.get('text','').split()) for p in pages)
            phases['extracted_characters']=sum(len(p.get('text','')) for p in pages)
            return pages
        finally:phases['extraction_seconds']=time.perf_counter()-begin; snap()
    def research(report,*args,**kwargs):
        # Reuse original extracted pages; no second extraction.
        paragraphs=[p['text'] for p in kwargs.get('pages_data',[]) if p.get('text','').strip()]
        stage[0]='ai_load'; begin=time.perf_counter()
        if model[0] is None:
            t=time.perf_counter()
            import torch
            phases['torch_import_seconds']=time.perf_counter()-t
            t=time.perf_counter()
            direct=os.environ.get('STAGE8J_DIRECT_TOKENIZER')=='1'
            if direct:
                from tools.stage8j_tokenizer import LocalFastTokenizer
            else:
                from transformers import AutoTokenizer
            phases['transformers_import_seconds']=time.perf_counter()-t
            t=time.perf_counter()
            torch.set_num_threads(2); torch.backends.quantized.engine='onednn'
            phases['thread_configuration_seconds']=time.perf_counter()-t
            hashes=json.loads((root/'scratch/stage8f/hashes_nawaf.json').read_text())
            artifact=root/'scratch/stage8h/nawaf_int8.jit'
            t=time.perf_counter(); verify_package(artifact,hashes['model.safetensors'],'int8')
            phases['artifact_verification_seconds']=time.perf_counter()-t
            from plagiarism_detector.ai_detection.sequence_research import SequenceResearchAdapter
            t=time.perf_counter(); guard=SequenceResearchAdapter(root/'scratch/stage8f/nawaf',file_hashes=hashes,label_mapping={0:'HUMAN',1:'AI_GENERATED'},mapping_evidence='publisher card')
            phases['source_asset_verification_seconds']=time.perf_counter()-t
            del guard
            t=time.perf_counter()
            tokenizer[0]=(LocalFastTokenizer(root/'scratch/stage8f/nawaf/tokenizer.json') if direct else AutoTokenizer.from_pretrained(str(root/'scratch/stage8f/nawaf'),local_files_only=True,trust_remote_code=False))
            phases['tokenizer_load_seconds']=time.perf_counter()-t
            t=time.perf_counter(); model[0]=torch.jit.load(str(artifact),map_location='cpu').eval()
            phases['model_file_load_seconds']=time.perf_counter()-t
        phases['ai_load_seconds']=time.perf_counter()-begin; snap()
        import torch
        stage[0]='ai_inference'; begin=time.perf_counter(); count=tokens=0
        with torch.inference_mode():
            for i in range(0,len(paragraphs),2):
                enc=tokenizer[0](paragraphs[i:i+2],padding=True,truncation=True,max_length=512,return_tensors='pt')
                scores=model[0](*(enc[k] for k in ('input_ids','attention_mask','token_type_ids')))
                assert scores.shape[-1]==2
                count+=scores.shape[0];tokens+=int(enc['attention_mask'].sum())
        phases.update(ai_seconds=time.perf_counter()-begin,ai_paragraphs=count,ai_tokens=tokens)
        snap(); stage[0]='report_processing'
        # Return original report exactly; research outputs never become findings.
        return report
    def analyze(*args,**kwargs):
        stage[0]='plagiarism'; begin=time.perf_counter()
        report=original_analyze(*args,**kwargs)
        phases['plagiarism_seconds']=time.perf_counter()-begin; snap()
        if not research_enabled:
            return report
        try:
            return research(report,*args,**kwargs)
        except Exception as exc:
            phases['research_error']=f'{type(exc).__name__}: {exc}'
            stage[0]='report_processing'
            return report
    monkeypatch.setattr(scan_routes,'extract_document_pages',extract)
    monkeypatch.setattr(scan_routes,'analyze_academic_document',analyze)
    monkeypatch.setattr(scan_routes,'get_current_settings',lambda:{**original_settings(),'enable_semantic_model':False,'enable_ocr':False})
    phrase='تتناول هذه الدراسة تحليل البيانات وتوثيق مصادر المعلومات ومراجعة النتائج باستخدام منهج واضح قابل للتحقق '
    try:
        with app.test_client() as client:
            for pages in (10,50,100):
                stage[0]='fixture_generation'
                document=fitz.open()
                words=(phrase.split()*10)[:100]
                for _ in range(pages):
                    page=document.new_page()
                    page.insert_htmlbox(fitz.Rect(40,40,550,780), '<div dir="rtl">'+' '.join(words)+'</div>')
                payload=document.tobytes(); document.close()
                if pages==10:repeat_payload=payload
                extracted[0]=0; phases.clear(); stage[0]='upload'; begin=time.perf_counter()
                response=client.post('/api/analyze',data={'file':(io.BytesIO(payload),f'synthetic-{pages}.pdf'),'title':f'Synthetic {pages} pages'},content_type='multipart/form-data')
                assert response.status_code==200, response.get_json()
                report=response.get_json()
                assert report['ai_analysis']['status']=='unavailable'
                assert extracted[0]==1
                assert 'research_error' not in phases,phases.get('research_error')
                runs.append({'pages':pages,'nominal_words':pages*100,'pdf_bytes':len(payload),'total_request_seconds':time.perf_counter()-begin,**phases,'overall_pct':report['overall_pct'],'production_ai_reason':report['ai_analysis']['reason']})
                if profiling:
                    (scratch/(os.environ.get('STAGE8J_CORPUS','empty')+'_progress.json')).write_text(json.dumps(runs,indent=2),encoding='utf-8')
                snap()
                runs[-1].update(request_end_rss=proc.memory_info().rss,request_end_private_bytes=getattr(proc.memory_info(),'private',0))
            if profiling and os.environ.get('STAGE8J_CORPUS')=='populated':
                from docx import Document
                doc=Document()
                for _ in range(10):doc.add_paragraph(' '.join(words))
                buffer=io.BytesIO();doc.save(buffer)
                scan=fitz.open();scan_page=scan.new_page()
                source_pdf=fitz.open(stream=payload,filetype='pdf')
                pix=source_pdf[0].get_pixmap(matrix=fitz.Matrix(2,2))
                scan_page.insert_image(scan_page.rect,stream=pix.tobytes('png'))
                scan_bytes=scan.tobytes();scan.close();source_pdf.close()
                extras=[('synthetic.docx',buffer.getvalue()),('synthetic-scanned.pdf',scan_bytes)]
                if os.environ.get('STAGE8K_REPEATED')=='1':
                    extras += [('repeat-1.docx',buffer.getvalue()),('repeat-2.docx',buffer.getvalue()),('repeat.pdf',repeat_payload)]
                for name,extra in extras:
                    extracted[0]=0;phases.clear();stage[0]='upload';begin=time.perf_counter()
                    response=client.post('/api/analyze',data={'file':(io.BytesIO(extra),name),'title':name},content_type='multipart/form-data')
                    row={'file_type':name,'status_code':response.status_code,'total_request_seconds':time.perf_counter()-begin,**phases}
                    if response.status_code==200:
                        assert extracted[0]==1
                        assert 'research_error' not in phases,phases.get('research_error')
                        row['overall_pct']=response.get_json()['overall_pct']
                        row['production_ai_reason']=response.get_json()['ai_analysis']['reason']
                    else:row['limitation']='upload/extraction did not produce a successful report'
                    runs.append(row);snap()
                    row.update(request_end_rss=proc.memory_info().rss,request_end_private_bytes=getattr(proc.memory_info(),'private',0))
                if os.environ.get('STAGE8K_REPEATED')=='1' and research_enabled:
                    model[0]=None
                    def unavailable_package(*args,**kwargs):
                        raise FileNotFoundError('injected missing research package')
                    verify_package=unavailable_package
                    phases.clear();extracted[0]=0;begin=time.perf_counter()
                    response=client.post('/api/analyze',data={'file':(io.BytesIO(repeat_payload),'failure-recovery.pdf')},content_type='multipart/form-data')
                    assert response.status_code==200,response.get_json()
                    assert response.get_json()['ai_analysis']['reason']=='disabled'
                    assert extracted[0]==1
                    assert response.get_json()['overall_pct']==runs[0]['overall_pct']
                    assert 'research_error' in phases
                    runs.append({'file_type':'injected missing research package','status_code':200,'total_request_seconds':time.perf_counter()-begin,'overall_pct':response.get_json()['overall_pct'],'production_ai_reason':response.get_json()['ai_analysis']['reason'],**phases})
        stage[0]='cleanup';model[0]=tokenizer[0]=None;gc.collect();snap()
        result={'startup_factory_seconds':startup,'baseline_process_rss':baseline_rss,'available_ram_before':available,'total_ram':psutil.virtual_memory().total,'runs':runs,'stage_peaks':measurements,'after_cleanup_rss':proc.memory_info().rss,'process_cpu_seconds':sum(proc.cpu_times()[:2])-cpu0,'elapsed_seconds':time.perf_counter()-started,'limitations':['Flask test client, not network server','test authentication/CSRF compatibility mode','antivirus test double','isolated empty corpus','semantic and OCR disabled','synthetic PDFs; no DOCX measurement','model cached after first request; score outputs discarded']}
        result.update(corpus_import_seconds=corpus_import_seconds,corpus_profile=os.environ.get('STAGE8J_CORPUS','empty'),sampling_interval=float(os.environ.get('BENCH_SAMPLE_SECONDS','.02')))
        result['direct_tokenizer']=os.environ.get('STAGE8J_DIRECT_TOKENIZER')=='1'
        result['workflow']='research' if research_enabled else 'plagiarism'
        import config
        from app.services import scan_service
        result['deployment_limits']={'max_concurrent_scans':config.MAX_CONCURRENT_SCANS,
            'max_concurrent_ocr':config.MAX_CONCURRENT_OCR_JOBS,
            'ocr_workers':config.PDF_OCR_WORKERS,'scan_executor_workers':scan_service._EXECUTOR._max_workers}
        if profiling:
            result['limitations']=['Flask test client; no network responsiveness measurement',
                'test authentication/CSRF mode and antivirus double',
                'synthetic authorized fixtures; not representative academic documents',
                'semantic model disabled; synchronous extraction may invoke OCR',
                'framework imports before factory timer excluded from startup measurement',
                'no target 4GB PC, system commit or page-file activity measurement',
                'cached research model; experimental outputs discarded']
        (scratch/(os.environ.get('STAGE8J_CORPUS','empty')+'_full_system.json' if profiling else 'full_system.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    finally:
        stop.set();thread.join()
