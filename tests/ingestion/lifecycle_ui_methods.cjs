/* Actual inline script; no network, cookies or hosted data. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const script=fs.readFileSync(process.argv[2],'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
class El{constructor(){this.children=[];this.textContent='';this.files=[];this.value='query';this.hidden=false;this.disabled=false;}append(...x){this.children.push(...x)}replaceChildren(...x){this.children=x}focus(){}}
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const ids={},get=id=>ids[id]??=new El();let deletes=0,fail=false,finish;
 const doc={document_id:'b'.repeat(64),filename:'<img src=x onerror=alert(1)>.txt',sha256:'c'.repeat(64),byte_size:17,chunk_count:1,mime_type:'text/plain'};
 let present=true;
 const resp=(x,status=200)=>({ok:status<400,status,json:async()=>x});
 const fetch=async(url,o={})=>{
  if(url==='/auth/status')return resp({csrf:'local',operations_enabled:true,email:'local@example.org'});
  if(o.method==='POST'&&url==='/documents')return fail?resp({error:'document_rejected'},422):resp({document_id:doc.document_id,filename:doc.filename,source_sha256:doc.sha256,extracted_sha256:'d'.repeat(64),byte_size:17,status:'stored',chunk_count:1,segment_count:1},201);
  if(o.method==='DELETE'){deletes++;await new Promise(r=>finish=r);present=false;return resp({status:'deleted'})}
  if(url==='/documents')return resp({documents:present?[doc]:[]});
  return resp(doc);
 };
 const ctx={document:{getElementById:get,createElement:()=>new El()},window:{fetch},location:{replace(){}},AbortController,setTimeout,clearTimeout,console};vm.createContext(ctx);vm.runInContext(script,ctx);await tick();await tick();
 let row=get('document-list').children[0],remove=row.children[2].children[1],box=row.children[4];remove.onclick();assert(!box.hidden);assert.equal(deletes,0);box.children[2].onclick();assert(box.hidden);assert.equal(deletes,0);
 remove.onclick();let pending=box.children[1].onclick();await tick();assert.equal(deletes,1);await box.children[1].onclick();assert.equal(deletes,1,'double confirm ignored');finish();await pending;assert.equal(get('document-list').children.length,0);
 get('file').files=[{name:doc.filename,size:17}];await get('upload').onclick();const receipt=get('upload-receipt');assert(!receipt.hidden);for(const x of ['201',doc.document_id,doc.sha256,doc.filename,'17'])assert(receipt.textContent.includes(x));assert.equal(receipt.children.length,0,'server strings rendered only as text');
 fail=true;await get('upload').onclick();assert(receipt.hidden);assert.equal(receipt.textContent,'','failed upload cannot retain previous success receipt');
 console.log(JSON.stringify({passed:true,in_page_cancel_zero_requests:true,confirm_one_request:true,duplicate_confirm_ignored:true,complete_server_receipt:true,hostile_filename_text_only:true,failed_upload_clears_receipt:true}));
})().catch(e=>{console.error(e);process.exit(1)});
