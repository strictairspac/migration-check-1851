import {api,post} from './client.js';
export const batches={list:()=>api('/batches'),save:(d,id)=>post('/batches'+(id?'/'+id:''),d,id?'PUT':'POST')};
export const mappings={list:()=>api('/mappings'),detail:id=>api('/mappings/'+id),save:(d,id)=>post('/mappings'+(id?'/'+id:''),d,id?'PUT':'POST'),dryRun:(id,candidateVersionId)=>post('/mappings/'+id+'/dry-runs',{candidate_version_id:candidateVersionId??null}),dryRuns:id=>api('/mappings/'+id+'/dry-runs')};
export const dryRuns={get:id=>api('/dry-runs/'+id),confirm:id=>post('/dry-runs/'+id+'/confirm',{})};
export const runs={list:()=>api('/runs'),run:d=>post('/runs',d),cancel:id=>post('/runs/'+id+'/cancel',{}),targets:id=>api('/runs/'+id+'/targets'),restore:(id,backup)=>post('/runs/'+id+'/restore',{backup})};
