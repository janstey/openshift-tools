# pylint: skip-file
# flake8: noqa

# pylint: skip-file

# pylint: disable=wrong-import-position,wrong-import-order
import base64

# pylint: disable=too-many-arguments
class OCSecret(OpenShiftCLI):
    ''' Class to wrap the oc command line tools
    '''
    def __init__(self,
                 namespace,
                 secret_name=None,
                 decode=False,
                 kubeconfig='/etc/origin/master/admin.kubeconfig',
                 verbose=False):
        ''' Constructor for OpenshiftOC '''
        super(OCSecret, self).__init__(namespace, kubeconfig)
        self.namespace = namespace
        self.name = secret_name
        self.kubeconfig = kubeconfig
        self.decode = decode
        self.verbose = verbose

    def get(self):
        '''return a secret by name '''
        results = self._get('secrets', self.name)
        results['decoded'] = {}
        results['exists'] = False
        if results['returncode'] == 0 and results['results'][0]:
            results['exists'] = True
            if self.decode:
                if results['results'][0].has_key('data'):
                    for sname, value in results['results'][0]['data'].items():
                        results['decoded'][sname] = base64.b64decode(value)

        if results['returncode'] != 0 and '"%s" not found' % self.name in results['stderr']:
            results['returncode'] = 0

        return results

    def delete(self):
        '''delete a secret by name'''
        return self._delete('secrets', self.name)

    def create(self, files=None, contents=None):
        '''Create a secret '''
        if not files:
            files = Utils.create_files_from_contents(contents)

        secrets = ["%s=%s" % (sfile['name'], sfile['path']) for sfile in files]
        cmd = ['secrets', 'new', self.name]
        cmd.extend(secrets)

        results = self.openshift_cmd(cmd)

        return results

    def update(self, files, force=False):
        '''run update secret

           This receives a list of file names and converts it into a secret.
           The secret is then written to disk and passed into the `oc replace` command.
        '''
        secret = self.prep_secret(files)
        if secret['returncode'] != 0:
            return secret

        sfile_path = '/tmp/%s' % self.name
        with open(sfile_path, 'w') as sfd:
            sfd.write(json.dumps(secret['results']))

        atexit.register(Utils.cleanup, [sfile_path])

        return self._replace(sfile_path, force=force)

    def prep_secret(self, files=None, contents=None):
        ''' return what the secret would look like if created
            This is accomplished by passing -ojson.  This will most likely change in the future
        '''
        if not files:
            files = Utils.create_files_from_contents(contents)

        secrets = ["%s=%s" % (sfile['name'], sfile['path']) for sfile in files]
        cmd = ['-ojson', 'secrets', 'new', self.name]
        cmd.extend(secrets)

        return self.openshift_cmd(cmd, output=True)

    @staticmethod
    # pylint: disable=too-many-return-statements,too-many-branches
    # TODO: This function should be refactored into its individual parts.
    def run_ansible(params, check_mode):
        '''run the ansible idempotent code'''

        ocsecret = OCSecret(params['namespace'],
                            params['name'],
                            params['decode'],
                            kubeconfig=params['kubeconfig'],
                            verbose=params['debug'])

        state = params['state']

        api_rval = ocsecret.get()

        #####
        # Get
        #####
        if state == 'list':
            return {'changed': False, 'results': api_rval, state: 'list'}

        if not params['name']:
            return {'failed': True,
                    'msg': 'Please specify a name when state is absent|present.'}

        ########
        # Delete
        ########
        if state == 'absent':
            if not Utils.exists(api_rval['results'], params['name']):
                return {'changed': False, 'state': 'absent'}

            if check_mode:
                return {'changed': True, 'msg': 'Would have performed a delete.'}

            api_rval = ocsecret.delete()
            return {'changed': True, 'results': api_rval, 'state': 'absent'}

        if state == 'present':
            if params['files']:
                files = params['files']
            elif params['contents']:
                files = Utils.create_files_from_contents(params['contents'])
            else:
                return {'failed': True,
                        'msg': 'Either specify files or contents.'}

            ########
            # Create
            ########
            if not Utils.exists(api_rval['results'], params['name']):

                if check_mode:
                    return {'changed': True,
                            'msg': 'Would have performed a create.'}

                api_rval = ocsecret.create(params['files'], params['contents'])

                # Remove files
                if files and params['delete_after']:
                    Utils.cleanup([ftmp['path'] for ftmp in files])

                if api_rval['returncode'] != 0:
                    return {'failed': True,
                            'msg': api_rval}

                return {'changed': True,
                        'results': api_rval,
                        'state': 'present'}

            ########
            # Update
            ########
            secret = ocsecret.prep_secret(params['files'], params['contents'])

            if secret['returncode'] != 0:
                return {'failed': True, 'msg': secret}

            if Utils.check_def_equal(secret['results'], api_rval['results'][0]):

                # Remove files
                if files and params['delete_after']:
                    Utils.cleanup([ftmp['path'] for ftmp in files])

                return {'changed': False,
                        'results': secret['results'],
                        'state': 'present'}

            if check_mode:
                return {'changed': True,
                        'msg': 'Would have performed an update.'}

            api_rval = ocsecret.update(files, force=params['force'])

            # Remove files
            if secret and params['delete_after']:
                Utils.cleanup([ftmp['path'] for ftmp in files])

            if api_rval['returncode'] != 0:
                return {'failed': True,
                        'msg': api_rval}

            return {'changed': True,
                    'results': api_rval,
                    'state': 'present'}

        return {'failed': True,
                'changed': False,
                'msg': 'Unknown state passed. %s' % state,
                'state': 'unknown'}
