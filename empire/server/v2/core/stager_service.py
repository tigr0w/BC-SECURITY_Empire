import copy
import os
import uuid
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from empire.server.database import models
from empire.server.v2.core.listener_service import ListenerService
from empire.server.v2.core.stager_template_service import StagerTemplateService


class StagerService(object):
    def __init__(self, main_menu):
        self.main_menu = main_menu

        self.stager_template_service: StagerTemplateService = (
            main_menu.stagertemplatesv2
        )
        self.listener_service: ListenerService = main_menu.listenersv2

    @staticmethod
    def get_all(db: Session):
        return db.query(models.Stager).all()

    @staticmethod
    def get_by_id(db: Session, uid: int):
        return db.query(models.Stager).filter(models.Stager.id == uid).first()

    @staticmethod
    def get_by_name(db: Session, name: str):
        return db.query(models.Stager).filter(models.Stager.name == name).first()

    def validate_stager_options(
        self, db: Session, template: str, params: Dict
    ) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
        """
        Validates the new listener's options. Constructs a new "Listener" object.
        :param template:
        :param params:
        :return:
        """
        if not self.stager_template_service.get_stager_template(template):
            return None, f"Stager Template {template} not found"

        if params.get("Listener") and not self.listener_service.get_by_name(
            db, params["Listener"]
        ):
            return None, f'Listener {params["Listener"]} not found'

        template_instance = self.stager_template_service.new_instance(template)

        return self._validate(template_instance, params)

    @staticmethod
    def _validate(instance, params: Dict):
        options = {}

        for option, option_value in instance.options.items():
            if option in params:
                if (
                    option_value["Strict"]
                    and params[option] not in option_value["SuggestedValues"]
                ):
                    return None, f"{option} must be set to one of the suggested values."
                elif option_value["Required"] and not params[option]:
                    return None, f"required stager option missing: {option}"
                else:
                    options[option] = params[option]
            elif option_value["Required"]:
                return None, f"required stager option missing: {option}"

        revert_options = {}
        for key, value in options.items():
            revert_options[key] = instance.options[key]["Value"]
            instance.options[key]["Value"] = value

        # todo We should update the validate_options method to also return a string error
        # todo stager instances don't have a validate method. but they COULD!
        # if not instance.validate_options():
        #     for key, value in revert_options.items():
        #         instance.options[key]['Value'] = value
        #     return None, 'Validation failed'

        return instance, None

    def create_stager(self, db: Session, stager_req, save: bool, user_id: int):
        if save and self.get_by_name(db, stager_req.name):
            return None, f"Stager with name {stager_req.name} already exists."

        template_instance, err = self.validate_stager_options(
            db, stager_req.template, stager_req.options
        )

        if err:
            return None, err

        generated, err = self.generate_stager(template_instance)

        if err:
            return None, err

        stager_options = copy.deepcopy(template_instance.options)
        stager_options = dict(
            map(lambda x: (x[0], x[1]["Value"]), stager_options.items())
        )

        db_stager = models.Stager(
            name=stager_req.name,
            module=stager_req.template,
            options=stager_options,
            one_liner=stager_options.get("OutFile", "") == "",
            user_id=user_id,
        )

        download = models.Download(
            location=generated,
            filename=generated.split("/")[-1],
            size=os.path.getsize(generated),
        )
        db.add(download)
        db.flush()
        db_stager.downloads.append(download)

        if save:
            db.add(db_stager)
            db.flush()
        else:
            db_stager.id = 0

        return db_stager, None

    def update_stager(self, db: Session, db_stager: models.Stager, stager_req):
        if stager_req.name != db_stager.name:
            if not self.get_by_name(db, stager_req.name):
                db_stager.name = stager_req.name
            else:
                return None, f"Stager with name {stager_req.name} already exists."

        template_instance, err = self.validate_stager_options(
            db, db_stager.module, stager_req.options
        )

        if err:
            return None, err

        generated, err = self.generate_stager(template_instance)

        if err:
            return None, err

        stager_options = copy.deepcopy(template_instance.options)
        stager_options = dict(
            map(lambda x: (x[0], x[1]["Value"]), stager_options.items())
        )
        db_stager.options = stager_options

        download = models.Download(
            location=generated,
            filename=generated.split("/")[-1],
            size=os.path.getsize(generated),
        )
        db.add(download)
        db.flush()
        db_stager.downloads.append(download)

        return db_stager, None

    def generate_stager(self, template_instance):
        resp = template_instance.generate()

        # todo generate should return error response much like listener validate options should.
        if resp == "" or resp is None:
            return None, "Error generating"

        out_file = template_instance.options.get("OutFile", {}).get("Value")
        if out_file and len(out_file) > 0:
            file_name = template_instance.options["OutFile"]["Value"].split("/")[-1]
        else:  # todo use a better default name
            file_name = f"{uuid.uuid4()}.txt"

        # TODO VR should this should be pulled from empire_config instead of main_menu
        file_name = (
            f"{self.main_menu.directory['downloads']}generated-stagers/{file_name}"
        )
        os.makedirs(os.path.dirname(file_name), exist_ok=True)
        mode = "w" if type(resp) == str else "wb"
        with open(file_name, mode) as f:
            f.write(resp)

        return file_name, None

    @staticmethod
    def delete_stager(db: Session, stager: models.Stager):
        db.delete(stager)
