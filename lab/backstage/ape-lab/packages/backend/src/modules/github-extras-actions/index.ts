/**
 * github:extras:* scaffolder actions used by APE's shared template steps.
 *
 * APE's `backstage-templates/shared/entities/{clone,commit,push}.yaml` invoke
 * `github:extras:clone`, `github:extras:commit`, `github:extras:push`. Those
 * actions live in an internal APE scaffolder backend module that isn't
 * shipped in this lab. To run the synced templates here, we provide thin
 * lab equivalents -- clone uses Backstage's built-in `cloneRepo` helper,
 * commit and push exec `git` directly inside the workspace folder cloned
 * by the first step. Auth piggy-backs on the GitHub integration credentials
 * Backstage already loads from app-config.integrations.github[0].token.
 */
import {
  coreServices,
  createBackendModule,
} from '@backstage/backend-plugin-api';
import {
  DefaultGithubCredentialsProvider,
  ScmIntegrations,
} from '@backstage/integration';
import {
  createTemplateAction,
  scaffolderActionsExtensionPoint,
} from '@backstage/plugin-scaffolder-node';
import { exec as execCb } from 'child_process';
import * as path from 'path';
import { promisify } from 'util';

const exec = promisify(execCb);

async function tokenFor(
  url: string,
  provider: DefaultGithubCredentialsProvider,
): Promise<string> {
  const creds = await provider.getCredentials({ url });
  const token = creds?.token;
  if (!token) {
    throw new Error(
      `No GitHub credentials resolved for ${url}; ` +
        `check integrations.github[].token in app-config`,
    );
  }
  return token;
}

function resolveDir(workspacePath: string, folder?: string): string {
  return folder ? path.join(workspacePath, folder) : workspacePath;
}

export const githubExtrasActionsModule = createBackendModule({
  pluginId: 'scaffolder',
  moduleId: 'github-extras-actions',
  register(reg) {
    reg.registerInit({
      deps: {
        scaffolderActions: scaffolderActionsExtensionPoint,
        config: coreServices.rootConfig,
        logger: coreServices.logger,
      },
      async init({ scaffolderActions, config, logger }) {
        const integrations = ScmIntegrations.fromConfig(config);
        const ghCreds =
          DefaultGithubCredentialsProvider.fromIntegrations(integrations);

        scaffolderActions.addActions(
          createTemplateAction({
            id: 'github:extras:clone',
            description: 'Clone a GitHub repo into the workspace.',
            schema: {
              input: {
                url: z =>
                  z.string({ description: 'HTTPS URL of the repo to clone.' }),
                branch: z =>
                  z
                    .string({ description: 'Branch / ref to check out.' })
                    .optional(),
                folder: z =>
                  z
                    .string({
                      description:
                        'Subfolder of the workspace to clone into. Defaults to the workspace root.',
                    })
                    .optional(),
              },
            },
            async handler(ctx) {
              const { url, branch, folder } = ctx.input as {
                url: string;
                branch?: string;
                folder?: string;
              };
              const dir = resolveDir(ctx.workspacePath, folder);
              const token = await tokenFor(url, ghCreds);

              // Embed the token in the HTTPS URL and clone via the system git
              // CLI. Backstage's isomorphic-git path (cloneRepo + auth:{token})
              // hits HTTP 401 against github.com here -- the standard git CLI
              // with token-in-URL authenticates reliably and is what commit /
              // push below already use, so we keep one auth path everywhere.
              const authedUrl = url.replace(
                /^https:\/\//,
                `https://x-access-token:${token}@`,
              );
              const refArgs = branch
                ? `--branch ${JSON.stringify(branch)} --single-branch`
                : '';
              ctx.logger.info(
                `Cloning ${url} (${branch ?? 'default'}) -> ${dir}`,
              );
              await exec(
                `git clone --depth 1 ${refArgs} ${JSON.stringify(authedUrl)} ${JSON.stringify(dir)}`,
              );
              // The token stays embedded in origin's URL inside the
              // workspace's .git/config so subsequent push can reuse it.
              // The scaffolder removes the workspace after the task ends,
              // so this exposure is short-lived and process-local.
            },
          }),

          createTemplateAction({
            id: 'github:extras:commit',
            description:
              'Stage every change in the workspace folder and create a commit.',
            schema: {
              input: {
                folder: z =>
                  z
                    .string({
                      description:
                        'Workspace subfolder that contains the cloned repo.',
                    })
                    .optional(),
                message: z =>
                  z
                    .string({ description: 'Commit message.' })
                    .optional()
                    .default('scaffolder-generated change'),
                gitAuthorName: z => z.string().optional(),
                gitAuthorEmail: z => z.string().optional(),
              },
            },
            async handler(ctx) {
              const { folder, message, gitAuthorName, gitAuthorEmail } =
                ctx.input as {
                  folder?: string;
                  message?: string;
                  gitAuthorName?: string;
                  gitAuthorEmail?: string;
                };
              const dir = resolveDir(ctx.workspacePath, folder);
              const name = gitAuthorName?.trim() || 'APE Scaffolder';
              const email = gitAuthorEmail?.trim() || 'scaffolder@ape.local';
              const msg = (message ?? '').trim() || 'scaffolder-generated change';

              const run = async (cmd: string) => {
                const { stdout, stderr } = await exec(cmd, { cwd: dir });
                if (stdout) ctx.logger.info(stdout.trim());
                if (stderr) ctx.logger.info(stderr.trim());
              };

              await run(`git config user.name ${JSON.stringify(name)}`);
              await run(`git config user.email ${JSON.stringify(email)}`);
              await run('git add -A');
              // git commit exits non-zero with "nothing to commit" -- catch
              // that specific case and treat it as a no-op so scaffolder
              // runs that produce no changes don't fail the whole task.
              try {
                await run(`git commit -m ${JSON.stringify(msg)}`);
              } catch (err: any) {
                const out = (err.stdout ?? '') + (err.stderr ?? '');
                if (/nothing to commit/i.test(out) || /no changes added/i.test(out)) {
                  ctx.logger.info('Nothing to commit — skipping.');
                  return;
                }
                throw err;
              }
            },
          }),

          createTemplateAction({
            id: 'github:extras:push',
            description: 'Push the workspace folder repo to its origin remote.',
            schema: {
              input: {
                folder: z =>
                  z
                    .string({
                      description:
                        'Workspace subfolder that contains the cloned repo.',
                    })
                    .optional(),
                branch: z =>
                  z
                    .string({
                      description:
                        'Branch to push. Defaults to the currently checked-out branch.',
                    })
                    .optional(),
              },
            },
            async handler(ctx) {
              const { folder, branch } = ctx.input as {
                folder?: string;
                branch?: string;
              };
              const dir = resolveDir(ctx.workspacePath, folder);
              const target = branch ?? 'HEAD';
              ctx.logger.info(`Pushing ${dir} -> origin ${target}`);
              const { stdout, stderr } = await exec(
                `git push origin ${JSON.stringify(target)}`,
                { cwd: dir },
              );
              if (stdout) ctx.logger.info(stdout.trim());
              if (stderr) ctx.logger.info(stderr.trim());
            },
          }),
        );

        logger.info(
          'github-extras-actions: registered github:extras:{clone,commit,push}',
        );
      },
    });
  },
});

export default githubExtrasActionsModule;
