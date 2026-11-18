import {store} from '../stores/business.js';
import {esc,json} from '../utils/html.js';
import {table} from '../components/common/table.js';
import {mappings,dryRuns} from '../api/business.js';
import {feedback} from '../components/common/feedback.js';

// 页面状态只保留所选映射编号；试跑证据与确认结果都以服务端记录为准。
const ui={mappingId:null,detail:null,dryRuns:[],dryId:null,dry:null,loading:false,error:'',started:false};

const CHANGE_LABEL={unchanged:'无变化',changed:'目标值变化',new_rejection:'新增拒绝',resolved:'不再拒绝',both_rejected:'仍拒绝',reason_changed:'拒绝原因变化'};

export function comparePage(){return `<div id="compare-root">${shell()}</div>`;}

function shell(){
 const options=store.mappings.map(m=>`<option value="${m.id}" ${ui.mappingId===m.id?'selected':''}>${esc(m.name)}</option>`).join('');
 return `<section class="compare-head"><div><span class="eyebrow">RULE TRIAL / NO TARGET WRITES</span><h2>同一批次，新旧规则并排试跑</h2><p>试跑只读取批次快照并逐行比对，不写目标行、不生成备份、不排入迁移队列。批次或任一套规则在试跑后有过改动，本次试跑即失效。</p></div><label class="inline-select">字段映射<select id="compare-mapping">${options}</select></label></section>${ui.error?`<div class="feedback error">${esc(ui.error)}</div>`:''}${body()}`;
}

function body(){
 if(!store.mappings.length)return '<div class="empty"><h2>还没有字段映射</h2><p>先在字段映射页登记规则，再回来试跑。</p></div>';
 if(!ui.detail)return '<div class="empty">正在读取试跑证据…</div>';
 const detail=ui.detail;
 const active=detail.versions.find(v=>v.state==='active');
 const candidate=(ui.dry?detail.versions.find(v=>v.id===ui.dry.candidate_version_id&&v.state==='candidate'):null)||detail.pending_version||detail.versions.find(v=>v.state==='candidate');
 return `${versionsPanel(detail,active,candidate)}${ui.dry?dryPanel(ui.dry):''}${historyPanel()}`;
}

function versionsPanel(detail,active,candidate){
 const batch=store.batches.find(b=>b.id===detail.batch_id);
 const canTrial=store.user.role!=='viewer'&&candidate;
 return `<div class="trial-grid"><section class="rule-card"><header><span class="eyebrow">IN USE</span><h3>在用规则</h3></header><p class="muted">版本 v${active?.version_no??'—'} · 每块 ${active?.chunk_size??'—'} 行</p><pre>${json(active?.rules??[])}</pre></section><section class="rule-card candidate"><header><span class="eyebrow">CANDIDATE</span><h3>候选规则</h3></header>${candidate?`<p class="muted">版本 v${candidate.version_no} · 每块 ${candidate.chunk_size} 行 · 尚未启用</p><pre>${json(candidate.rules)}</pre>`:'<p>没有待确认的候选。到字段映射页编辑并保存规则会生成候选；在用规则不会被直接改动。</p>'}</section><section class="rule-card"><header><span class="eyebrow">BATCH</span><h3>批次快照</h3></header>${batch?`<p><b>${esc(batch.name)}</b><br><small>修订 ${batch.revision??1} · ${batch.rows.length} 行 · ${esc(batch.source_file)}</small></p><small class="muted">试跑会冻结批次内容摘要；之后任何编辑都使旧试跑失效。</small>`:'<p>批次不存在。</p>'}<div class="actions">${canTrial?`<button id="trial-start">用同一批次试跑新旧映射 →</button>`:'<button disabled title="没有候选或观察员只读">用同一批次试跑新旧映射 →</button>'}</div>${store.user.role==='viewer'?'<small class="muted">观察员只能查看既有试跑记录。</small>':''}</section></div>`;
}

function summaryCards(summary){
 const cards=[['新增拒绝',summary.new_rejections],['键碰撞',summary.new_key_collisions],['结果变化',summary.changed_rows],['不再拒绝',summary.resolved_rejections],['在用接受 / 候选接受',`${summary.base_accepted} / ${summary.candidate_accepted}`],['在用拒绝 / 候选拒绝',`${summary.base_rejected} / ${summary.candidate_rejected}`]];
 return `<div class="metrics trial">${cards.map(([label,value])=>`<div><small>${label}</small><strong>${value}</strong></div>`).join('')}</div>`;
}

function rowTable(rows){
 if(!rows.length)return '<div class="empty">无。</div>';
 return table(['原行号','变化','在用 → 候选','原行'],rows.map(e=>{
  const detail=e.change==='new_rejection'?`在用：接受<br>候选：拒绝 · <code>${esc(e.candidate_reason)}</code>`:e.change==='resolved'?`在用：拒绝 · <code>${esc(e.base_reason)}</code><br>候选：接受`:e.change==='changed'?`改变字段：${esc((e.changed_fields||[]).join('、'))}<br><small>在用 ${esc(JSON.stringify(e.base_target))}<br>候选 ${esc(JSON.stringify(e.candidate_target))}</small>`:e.change==='reason_changed'?`<code>${esc(e.base_reason)}</code> → <code>${esc(e.candidate_reason)}</code>`:`<code>${esc(e.base_reason||e.candidate_reason||'')}</code>`;
  const flag=e.key_collision?'<div class="tag collision">键碰撞</div>':'';
  return [e.row_number,`<b>${CHANGE_LABEL[e.change]||e.change}</b>${flag}`,detail,`<details><summary>展开原行</summary><pre>${json(e.source)}</pre></details>`];
 }));
}

function dryPanel(dry){
 const r=dry.result;
 const valid=dry.valid;
 const receipt=dry.activation;
 return `<div class="trial-result"><div class="result-head"><div><span class="eyebrow">TRIAL #${dry.id} / ${receipt?'APPLIED':valid?'VALID':'STALE'}</span><h2>试跑对比 ${statusTag(valid,!!receipt)}</h2></div><div class="actions">${valid&&!receipt&&store.user.role!=='viewer'?`<button id="trial-confirm">确认切换到候选 →</button>`:''}${receipt?`<span class="status completed">候选已启用</span>`:''}</div></div><p class="muted">批次 ${esc(r.batch.name)} · 修订 ${r.batch.revision} · 源行 ${r.batch.source_count}；试跑不写目标表、不生成备份、不排入队列。批次或任一套规则在试跑后有改动，确认会被拒绝。</p>${summaryCards(r.summary)}${!valid&&!receipt?`<div class="feedback error">试跑已失效：${esc((dry.stale_reasons||[]).join('；'))}。请重新试跑后再确认。</div>`:''}${receipt?`<div class="feedback">已启用候选 v${esc(String(receipt.to_version_id))}（凭据 #${receipt.id}，${esc(receipt.created_at)}）。同一试跑重复确认不会再次启用。</div>`:''}<div class="checksum-row"><div><small>在用规则摘要</small><code class="checksum">${esc(r.base.rule_digest)}</code><small>在用结果 checksum</small><code class="checksum">${esc(r.base.checksum)}</code></div><div><small>候选规则摘要</small><code class="checksum">${esc(r.candidate.rule_digest)}</code><small>候选结果 checksum</small><code class="checksum">${esc(r.candidate.checksum)}</code></div></div><h3>新增拒绝 · 按原行核对</h3>${rowTable(r.new_rejections)}<h3>键碰撞</h3>${rowTable(r.key_collisions)}<h3>结果变化</h3>${rowTable(r.changed)}<h3>不再拒绝</h3>${rowTable(r.resolved)}${r.reason_changes.length?`<h3>拒绝原因变化</h3>${rowTable(r.reason_changes)}`:''}<details><summary>逐行完整对照 (${r.rows.length} 行)</summary>${rowTable(r.rows)}</details><details><summary>在用与候选的拒绝区</summary><pre>${json({base:r.base.rejected_rows,candidate:r.candidate.rejected_rows})}</pre></details></div>`;
}

function statusTag(valid,applied){return applied?'<span class="status completed">已启用</span>':valid?'<span class="status completed">有效</span>':'<span class="status failed">已失效</span>';}

function historyPanel(){
 if(!ui.dryRuns.length)return '';
 return `<section class="history"><h3>试跑记录</h3>${table(['试跑','批次修订','在用 / 候选','结论','操作'],ui.dryRuns.map(d=>[
  `#${d.id}<small>${esc(d.created_at)}</small>`,
  d.batch_revision,
  `v${d.result?.base?.version_no??'—'} → v${d.result?.candidate?.version_no??'—'}<small>新增拒绝 ${d.result?.summary?.new_rejections??'—'} · 键碰撞 ${d.result?.summary?.new_key_collisions??'—'} · 变化 ${d.result?.summary?.changed_rows??'—'}</small>`,
  d.applied?'<span class="status completed">已启用</span>':d.valid?'<span class="status">有效</span>':`<span class="status failed">已失效</span><small>${esc((d.stale_reasons||[]).join('；'))}</small>`,
  `<button class="quiet" data-open-dry="${d.id}">查看对比</button>`,
 ]))}</section>`;
}

function paint(){
 const root=document.getElementById('compare-root');
 if(!root)return;
 root.innerHTML=shell();
 bind(root);
}

function bind(root){
 const select=root.querySelector('#compare-mapping');
 if(select)select.onchange=async()=>{ui.mappingId=Number(select.value);ui.dry=null;ui.dryId=null;ui.detail=null;ui.dryRuns=[];await load();};
 root.querySelector('#trial-start')?.addEventListener('click',async()=>{
  try{const dry=await mappings.dryRun(ui.mappingId,ui.detail?.pending_version?.id??null);ui.dryId=dry.id;await load();feedback('试跑完成：未写目标行、未生成备份、未排队。');}
  catch(e){feedback(e.message,true);}
 });
 root.querySelector('#trial-confirm')?.addEventListener('click',async()=>{
  try{
   const r=await dryRuns.confirm(ui.dryId);
   await load();
   feedback(r.activated?'已切换到候选规则。此后受理的运行使用新版；已排队的运行仍沿用它受理时的规则。':(r.already_applied?'该试跑已经启用过，本次未重复启用。':'未切换。'));
  }catch(e){feedback(e.message,true);await load();}
 });
 root.querySelectorAll('[data-open-dry]').forEach(b=>b.onclick=async()=>{try{ui.dryId=Number(b.dataset.openDry);await load();}catch(e){feedback(e.message,true);}});
}

export async function mountCompare(){
 // 首次进入时初始化所选映射，之后保留用户选择。
 if(!ui.started){ui.started=true;if(!ui.mappingId||!store.mappings.some(m=>m.id===ui.mappingId))ui.mappingId=store.mappings[0]?.id??null;}
 if(!ui.mappingId){paint();return;}
 await load();
}

async function load(){
 if(ui.loading)return;
 ui.loading=true;ui.error='';
 try{
  const [detail,list]=await Promise.all([mappings.detail(ui.mappingId),mappings.dryRuns(ui.mappingId)]);
  ui.detail=detail;ui.dryRuns=list;
  // 初次进入或切换映射时，默认展开最近一次试跑证据。
  if(!ui.dryId&&list.length)ui.dryId=list[0].id;
  if(ui.dryId){const summary=list.find(d=>d.id===ui.dryId);ui.dry=summary?await dryRuns.get(ui.dryId):null;}
 }catch(e){ui.error=e.message;}
 finally{ui.loading=false;}
 paint();
}
