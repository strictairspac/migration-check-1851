/** @typedef {{id:number,name:string,source_file:string,rows:object[]}} Batch */
/** @typedef {{id:number,name:string,batch_id:number,rules:object[],chunk_size:number,active_version_id:number|null,active_version:MappingVersion|null,pending_version:MappingVersion|null}} Mapping */
/** @typedef {{id:number,mapping_id:number,version_no:number,rules:object[],chunk_size:number,rule_digest:string,state:'active'|'candidate'|'archived'|'withdrawn',batch_revision:number|null}} MappingVersion */
/** @typedef {{id:number,mapping_id:number,batch_id:number,base_version_id:number,candidate_version_id:number,batch_revision:number,base_rule_digest:string,candidate_rule_digest:string,result:object,valid?:boolean,stale_reasons?:string[],activation:object|null}} DryRun */
/** @typedef {{id:number,name:string,status:'queued'|'running'|'completed'|'failed'|'cancelled',mapping_version_id:number|null,snapshot:object,result:object|null}} Run */
export {};
