/* Local DOM regression for real candidate script, no network or credentials. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2],'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
class El{constructor(){this.children=[];this.textContent='';this.value='question';this.files=[];this.disabled=false;this.hidden=false;}focus(){}append(...x){this.children.push(...x)}replaceChildren(...x){this.children=x}}
const doc={document_id:'a'.repeat(64),filename:'fabricated.txt',byte_size:10,chunk_count:1,mime_type:'text/plain'};
const evidence={evidence:{entries:[{ref:'E1',citation:{source:{filename:doc.filename},start:0,end:10},locator:{kind:'document'},score:1,text:'fabricated deleted text'}]}};
const tick=()=>new Promise(r=>setImmediate(r));
async function scenario(mode){
 const ids={};const get=id=>ids[id]??=new El();let deleted=false,release,delay=false;
 const blocked=new Promise(r=>release=r);
 const response=x=>({ok:true,status:200,json:async()=>x});
 const fetch=async(url,options={})=>{
  if(url==='/auth/status')return response({csrf:'test',operations_enabled:true,email:'local@example.org'});
  if(url==='/query')return {ok:true,status:200,json:async()=>{if(delay){await blocked;if(mode==='error')throw Error('stale failure');}return evidence}};
  if(options.method==='DELETE'){deleted=true;return response({status:'deleted'})}
  if(url==='/documents'){
   const before={documents:deleted?[]:[doc]};
   return {ok:true,status:200,json:async()=>{if(delay&&mode==='list'&&!deleted)await blocked;return before}};
  }
  throw Error('unexpected route');
 };
 const c={document:{getElementById:get,createElement:()=>new El()},window:{fetch,confirm:()=>true},location:{replace:()=>{}},console};
 vm.createContext(c);vm.runInContext(script,c);await tick();await tick();
 const row=get('document-list').children[0];assert(row,'initial row');
 // First actually display retrieval, not an empty result placeholder.
 await get('search').onclick();assert.equal(get('results').children.length,1,'retrieval displayed');
 delay=true;
 const pending=mode==='list'?get('refresh-documents').onclick():get('search').onclick();
 await tick();await row.children[2].children[1].onclick();await row.children[4].children[1].onclick();
 assert(deleted);assert.equal(get('results').children.length,0);
 assert.equal(get('document-list').children.length,0);
 const status=get('query-status').textContent;
 release();await pending;
 assert.equal(get('results').children.length,0,'late predelete result must not repaint');
 assert.equal(get('document-list').children.length,0,'late predelete list must not resurrect row');
 assert.equal(get('query-status').textContent,status,'stale error/result must not replace rerun notice');
 // A new postdelete request is not permanently suppressed.
 delay=false;
 if(mode!=='list'){await get('search').onclick();assert.equal(get('results').children.length,1,'new request processed');}
 return {scenario:mode,displayed_before_delete:true,late_response_ignored:true};
}
(async()=>{const result=[];for(const mode of ['query','error','list'])result.push(await scenario(mode));console.log(JSON.stringify({passed:true,results:result},null,2))})().catch(e=>{console.error(e);process.exit(1)});
