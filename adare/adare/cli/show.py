# # external imports
# import pandas as pd
# from pathlib import Path
# import rich
#
# # internal imports
# from adare.backend.basics import determine_projectdirectory
# from adare.backend.projectold import Project
# from adare.helperFunctions.cli import print_df, print_dict, get_status_icon
# from adare.database.api.project import ProjectManagementApi
# from adare.backend.environment import Environment
#
# import logging
# log = logging.getLogger(__name__)
#
#
#
#
# def exec_show_project(arguments):
#     """
#     shows the information about projects
#
#     :param arguments: arguments parsed via input
#     """
#     with ProjectManagementApi() as api:
#         projects = api.get_projects()
#         columns = ['name', 'path', 'description']
#         projects_data = [[project.name, project.path, project.description] for project in projects]
#     df_projects = pd.DataFrame(projects_data, columns=columns)
#     print_df(df_projects, 'Projects')
#
#
# def exec_show_env(arguments):
#     """
#     shows the information about environments of a given project
#
#     :param arguments: arguments parsed via input
#     """
#
#     project_path = determine_projectdirectory(arguments.project)
#
#     with ProjectManagementApi() as api:
#         project = api.get_project_by_path(project_path)
#
#         # update experiments for all environments
#         if project:
#             for env in project.environments:
#                 Environment(env.name, Path(project.path))
#
#             columns = ['name', 'description', 'path', 'experiments']
#             env_data = []
#             if project.environments:
#                 for env in project.environments:
#                     env_data.append([env.name, env.description, env.path, "\n".join([exp.name for exp in env.experiments])])
#             df_env = pd.DataFrame(env_data, columns=columns)
#
#             print_df(df_env, f'Environments (project {project.name})')
#         else:
#             if arguments.project:
#                 print(f'Project {arguments.project} not found.')
#             else:
#                 print(f'Project in cwd ({Path().cwd()}) not found.')
#
#
# def exec_show_experiment(arguments):
#     """
#     shows the information about a specific experiment
#
#     :param arguments: arguments parsed via input
#     """
#     project_path = determine_projectdirectory(arguments.project)
#     if not project_path:
#         print(f'Project {arguments.project} not found.')
#         exit(-1)
#     project_name = Path(project_path).name
#
#     with ProjectManagementApi() as db:
#         exp = db.get_experiment_in_env(project_name=project_name, env_name=arguments.environment, experiment_name=arguments.experiment)
#         if not exp:
#             print(f'Experiment {arguments.experiment} not found.')
#             exit(-1)
#         else:
#             # print metadata such as name, description and run count in a rich table
#             metadata = {
#                 'name': exp.name,
#                 'description': exp.description,
#                 'run count': len(exp.runs)
#             }
#             print_dict(metadata, 'Experiment Metadata')
#
#
# def exec_show_runs(arguments):
#     """
#     shows the information about experiment runs of a given project
#
#     :param arguments: arguments parsed via input
#     """
#     project_path = determine_projectdirectory(arguments.project)
#     if not project_path:
#         print(f'Project {arguments.project} not found.')
#         exit(-1)
#     project_name = Path(project_path).name
#
#     with ProjectManagementApi() as db:
#         runs = db.get_experiment_runs(project_name=project_name, env_name=arguments.environment, experiment_name=arguments.experiment)
#         if not runs:
#             print(f'No runs found.')
#             exit(-1)
#         else:
#             exp = db.get_experiment_in_env(project_name=project_name, env_name=arguments.environment, experiment_name=arguments.experiment)
#             run_counts = db.get_experiment_run_counts_by_status(exp.uuid)
#             # change keys to status emoji and name
#             run_counts_dict = {
#                 get_status_icon('success'): run_counts['success'],
#                 get_status_icon('failed'): run_counts['failed'],
#             }
#             # add the other
#             for status in run_counts.keys():
#                 if status not in ['success', 'failed']:
#                     run_counts_dict[get_status_icon(status)] = run_counts[status]
#
#             print('')
#             print_dict(run_counts_dict, 'Run Counts')
#
#             # print metadata such as name, description and run count in a rich table
#             columns = ['uuid', 'experiment',  'status', 'published']
#             run_data = [
#                 [
#                     run.uuid,
#                     run.experiment.name,
#                     get_status_icon(run.status.name) if not arguments.no_emoji else run.status.name,
#                     get_status_icon(run.publish_status.name) if not arguments.no_emoji else run.publish_status.name,
#                 ]
#                 for run in runs
#             ]
#             df_runs = pd.DataFrame(run_data, columns=columns)
#
#             print('')
#             print_df(df_runs, 'Runs')
#
#
# def exec_show_run_result(arguments):
#     """
#     shows the information about experiment run results of a given project
#     :param arguments:
#     :return:
#     """
#
#     with ProjectManagementApi() as db:
#         run = db.get_experiment_run_by_uuid(uuid=arguments.uuid)
#         if not run:
#             print(f'Run with uuid {arguments.uuid} not found.')
#             exit(-1)
#         else:
#             # print metadata such as name, description and run count in a rich table
#             metadata = {
#                 'uuid': run.uuid,
#                 'experiment': run.experiment.name,
#                 'status': get_status_icon(run.status.name) if arguments.no_emoji else run.status.name,
#                 'published': get_status_icon(run.publish_status.name) if arguments.no_emoji else run.publish_status.name,
#             }
#             print_dict(metadata, 'Run Metadata')
#
#             # print results for each test in a rich table
#             columns = [
#                 '',
#                 'name',
#                 'function',
#                 'parameter',
#                 'value',
#                 'details',
#             ]
#
#             result_data = [
#                 [
#                     get_status_icon(test.result.status.name, include_text=False) if not arguments.no_emoji else test.result.status.name,
#                     test.abstracttest.name,
#                     test.abstracttest.testfunction.name,
#                     "\n".join([
#                         f'{param.parameter.name}'
#                         for param in test.abstracttest.parameters
#                     ]),
#                     "\n".join([
#                         f'{param.value}'
#                         for param in test.abstracttest.parameters
#                     ]),
#                     test.result.details
#                 ]
#                 for test in run.tests
#             ]
#
#             df_results = pd.DataFrame(result_data, columns=columns)
#             print_df(df_results, 'Results')
#
#
# def exec_show_usb(arguments):
#     """
#     shows the information about usb drives
#
#     :param arguments: arguments parsed via input
#     """
#     with ProjectManagementApi() as db:
#         usb_devices = db.get_usb_drives()
#         columns = ['name', 'description', 'path']
#         usb_data = [[usb.name, usb.description, usb.path] for usb in usb_devices]
#     df_usb = pd.DataFrame(usb_data, columns=columns)
#     print_df(df_usb, 'USB Devices')
#
#
# def exec_show_smb(arguments):
#     """
#     shows the information about smb drives
#
#     :param arguments: arguments parsed via input
#     """
#     with ProjectManagementApi() as db:
#         smb_devices = db.get_smb_drives()
#         columns = ['name']
#         smb_data = [[smb.name] for smb in smb_devices]
#     df_smb = pd.DataFrame(smb_data, columns=columns)
#     print_df(df_smb, 'SMB Devices')
#
# def exec_show_nfs(arguments):
#     """
#     shows the information about nfs drives
#
#     :param arguments: arguments parsed via input
#     """
#     with ProjectManagementApi() as db:
#         nfs_devices = db.get_nfs_drives()
#         columns = ['name']
#         nfs_data = [[nfs.name] for nfs in nfs_devices]
#     df_nfs = pd.DataFrame(nfs_data, columns=columns)
#     print_df(df_nfs, 'NFS Devices')
