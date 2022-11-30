import dataclasses

from parseandtest.tester.Tester import Tester
import yamlfeatures as yml

from pathlib import Path
# t = TestResult("randomtest", "is_dir", "das ist der beste test der welt", TestSuccess(), "beschreibug", {'test': 'yo'})
#

if __name__ == '__main__':
    loader, dumper = yml.create_yaml_loader_dumper_inputfiles()
    data = yml.yaml_to_dict(r'D:\FKIE_Test\Tproj\environments\win10\input\deletefile.yml', loader=loader)
    print(data)
    t = Tester()
    t.set_input(data)
    # t.test()
    # print(t.outcome.TestResultList[0])
    # print(t[0]['params'][0].compare('2022-05-27 08:39:27.1690000'))
    # if type(t['name']) == yml.YamlRegexString:
    #     print(t['name'])

# f = HtmlResultFormatter(".")
# f.set_outcome(TestOutcome([t]))
# f.format_result()
