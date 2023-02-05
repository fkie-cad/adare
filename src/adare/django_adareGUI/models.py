from django.db import models
import uuid


class Status(models.Model):
    name = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return str(self.name)



class Result(models.Model):
    status = models.ForeignKey(Status, on_delete=models.PROTECT)
    details = models.CharField(max_length=2000, blank=True)

    def __str__(self):
        return str(self.status)



class TestParameter(models.Model):
    name = models.CharField(max_length=100, unique=True)
    dtype = models.CharField(max_length=50)

    def __str__(self):
        return str(self.name)



class TestParameterEntries(models.Model):
    parameter = models.ForeignKey(TestParameter, on_delete=models.PROTECT)
    value = models.CharField(max_length=2000)

    def __str__(self):
        return str(self.parameter)


class TestFunction(models.Model):
    name = models.CharField(max_length=100, unique=True)
    test_name = models.CharField(max_length=100, unique=True)
    test_description = models.CharField(max_length=1000)
    possible_parameters = models.ManyToManyField(TestParameter)

    def __str__(self):
        return str(self.name)


class Tool(models.Model):
    name = models.CharField(max_length=50)
    command = models.CharField(max_length=200)

    def __str__(self):
        return str(self.name)


class Test(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    testfunction = models.ForeignKey(TestFunction, on_delete=models.PROTECT)
    result = models.ForeignKey(Result, on_delete=models.PROTECT)
    description = models.CharField(max_length=500)
    parameters = models.ManyToManyField(TestParameterEntries)
    tool = models.ForeignKey(Tool, on_delete=models.PROTECT, null=True)

    def __str__(self):
        return str(self.name)


class OsInfo(models.Model):
    os = models.CharField(max_length=50)
    distribution = models.CharField(max_length=50)
    version = models.CharField(max_length=50, blank=True)
    language = models.CharField(max_length=50, blank=True)
    architecture = models.CharField(max_length=50, blank=True)
    details = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f'{self.os} - {self.distribution} {self.version} ({self.language, self.architecture})'


class Experiment(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    timestamp_start = models.DateTimeField()
    timestamp_end = models.DateTimeField()
    tests = models.ManyToManyField(Test)
    os_info = models.ForeignKey(OsInfo, on_delete=models.PROTECT)
    description = models.CharField(max_length=500)

    status = models.ForeignKey(Status, null=True, on_delete=models.SET_NULL, related_name='status')
    status_gui_automation = models.ForeignKey(Status, null=True, on_delete=models.SET_NULL,
                                              related_name='status_gui_automation')
    status_parse_and_test = models.ForeignKey(Status, null=True, on_delete=models.SET_NULL,
                                              related_name='status_parse_and_test')
    status_vagrant = models.ForeignKey(Status, null=True, on_delete=models.SET_NULL, related_name='status_vagrant')

    logfile_gui_automation = models.CharField(max_length=200, blank=True, null=True)
    logfile_parse_and_test = models.CharField(max_length=200, blank=True, null=True)
    logfile_vagrant = models.CharField(max_length=200, blank=True, null=True)
    logfile_installed_packages = models.CharField(max_length=200, blank=True, null=True)
    logfile_postsetup_installations = models.CharField(max_length=200, blank=True, null=True)
    logfile_run_experiment = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f'{self.uuid}'
