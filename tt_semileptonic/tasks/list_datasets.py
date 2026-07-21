from columnflow.core.tasks import BaseTask
from tt_semileptonic.config.run3.config_helper import get_datasets


@BaseTask(namespace="list_campaign")
def list_campaign(analysis_cfg, **kwargs):
       """List all datasets in the campaign_run3_2024_nano_v15."""
    campaign = analysis_cfg.campaign[campaign_name]
    
    datasets = get_datasets(campaign)
    
    print(f"\n=== Datasets ({len(datasets)} total) ===\n")
    for dataset in sorted(datasets):
        print(dataset)
        
    return {"datasets": datasets}
