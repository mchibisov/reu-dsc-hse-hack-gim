import {createHandler} from './handler.mjs';
// Deployment includes only the secret fingerprint, never the secret itself.
import config from './deployment-config.json' with {type:'json'};
Deno.serve(createHandler(config));
