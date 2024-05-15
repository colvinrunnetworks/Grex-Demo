import asyncio
import json
import logging
import os
import sys
import time
from aiohttp import ClientError

import random

from datetime import date
from uuid import uuid4


TAILS_FILE_COUNT = int(os.getenv("TAILS_FILE_COUNT", 100))
CRED_PREVIEW_TYPE = "https://didcomm.org/issue-credential/2.0/credential-preview"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa

from runners.agent_container import (  # noqa:E402
    arg_parser,
    create_agent_with_args,
    AriesAgent,
)
from runners.support.utils import (  # noqa:E402
    check_requires,
    log_msg,
    log_status,
    log_timer,
    prompt,
    prompt_loop,
)


CRED_PREVIEW_TYPE = "https://didcomm.org/issue-credential/2.0/credential-preview"
SELF_ATTESTED = os.getenv("SELF_ATTESTED")
TAILS_FILE_COUNT = int(os.getenv("TAILS_FILE_COUNT", 100))


logging.basicConfig(level=logging.WARNING)
LOGGER = logging.getLogger(__name__)




class AcmeAgent(AriesAgent):
    CREDS = True
    MISSION_DETAILS = ''
    MISSION_COMPLETED = False
    def __init__(
        self,
        ident: str,
        http_port: int,
        admin_port: int,
        no_auto: bool = False,
        **kwargs,
    ):
        super().__init__(
            ident,
            http_port,
            admin_port,
            prefix="Ground Control Station (2)",
            no_auto=no_auto,
            **kwargs,
        )
        self.connection_id = None
        self._connection_ready = None
        self.cred_state = {}
        self.cred_attrs = {}

    async def detect_connection(self):
        await self._connection_ready
        self._connection_ready = None

    @property
    def connection_ready(self):
        return self._connection_ready.done() and self._connection_ready.result()

    async def handle_oob_invitation(self, message):
        pass

    # Method to get the value of CREDS
    @classmethod
    def get_creds(cls):
        return cls.CREDS

    # Method to set the value of CREDS
    @classmethod
    def set_creds(cls, value):
        cls.CREDS = value

        # Method to get the value of MISSION_COMPLETED
    @classmethod
    def get_mission_completed(mss):
        return mss.MISSION_COMPLETED

    # Method to set the value of MISSION_COMPLETED
    @classmethod
    def set_mission_completed(mss, value):
        mss.MISSION_COMPLETED = value

        # Method to get the value of MISSION_DETAILS
    @classmethod
    def get_mission_details(dts):
        return dts.MISSION_DETAILS

    # Method to set the value of MISSION_DETAILS
    @classmethod
    def set_mission_details(dts, value):
        dts.MISSION_DETAILS = value

    async def handle_connections(self, message):
        print(
            self.ident, "handle_connections", message["state"], message["rfc23_state"]
        )
        conn_id = message["connection_id"]
        if (not self.connection_id) and message["rfc23_state"] == "invitation-sent":
            print(self.ident, "set connection id", conn_id)
            self.connection_id = conn_id
        if (
            message["connection_id"] == self.connection_id
            and message["rfc23_state"] == "completed"
            and (self._connection_ready and not self._connection_ready.done())
        ):
            self.log("Connected")
            self._connection_ready.set_result(True)
            log_status("#7 Request proof of certification from drone")
            req_attrs = [
                {
                    "name": "id",
                    "restrictions": [{"schema_name": "drone schema"}]
                },
                {
                    "name": "date",
                    "restrictions": [{"schema_name": "drone schema"}]
                },
                {
                    "name": "branch_approval",
                    "restrictions": [{"schema_name": "drone schema"}]
                },
                {
                    "name": "circulation_start_dateint",
                    "restrictions": [{"schema_name": "drone schema"}]
                },
                {
                    "name": "mission_type",
                    "restrictions": [{"schema_name": "drone schema"}]
                }
            ]
            req_preds = []
            indy_proof_request = {
                "name": "Proof of Certification",
                "version": "1.0",
                "nonce": str(uuid4().int),
                "requested_attributes": {
                    f"0_{req_attr['name']}_uuid": req_attr
                    for req_attr in req_attrs
                },
                "requested_predicates": {}
            }
            proof_request_web_request = {
                "connection_id": self.connection_id,
                "presentation_request": {"indy": indy_proof_request},
            }
            # this sends the request to our agent, which forwards it to Alice
            # (based on the connection_id)
            await self.admin_POST(
                "/present-proof-2.0/send-request",
                proof_request_web_request
            )

    async def handle_issue_credential_v2_0(self, message):
        state = message["state"]
        cred_ex_id = message["cred_ex_id"]
        prev_state = self.cred_state.get(cred_ex_id)
        if prev_state == state:
            return  # ignore
        self.cred_state[cred_ex_id] = state

        self.log(f"Credential: state = {state}, cred_ex_id = {cred_ex_id}")

        if state == "request-received":
            # issue credentials based on offer preview in cred ex record
            if not message.get("auto_issue"):
                await self.admin_POST(
                    f"/issue-credential-2.0/records/{cred_ex_id}/issue",
                    {"comment": f"Issuing credential, exchange {cred_ex_id}"},
                )

    async def handle_issue_credential_v2_0_indy(self, message):
        pass  # employee id schema does not support revocation


    async def handle_present_proof_v2_0(self, message):
        state = message["state"]
        pres_ex_id = message["pres_ex_id"]
        self.log(f"Presentation: state = {state}, pres_ex_id = {pres_ex_id}")

        if state == "presentation-received":
            log_status("#11 Process the proof provided by X")
            log_status("#12 Check if proof is valid")
            proof = await self.admin_POST(
                f"/present-proof-2.0/records/{pres_ex_id}/verify-presentation"
            )
            self.log("Proof = ", proof["verified"])
            if ('true' not in proof["verified"]):
                self.set_creds(False)
                # await asyncio.sleep(1)
                # sys.exit(1)

            # if presentation is a degree schema (proof of education),
            # check values received
            pres_req = message["by_format"]["pres_request"]["indy"]
            pres = message["by_format"]["pres"]["indy"]
            is_proof_of_certification = (
                pres_req["name"] == "Proof of Certification"
            )
            if is_proof_of_certification:
                log_status("#13 Received proof of certification, check claims")
                for (referent, attr_spec) in pres_req["requested_attributes"].items():
                    if referent in pres['requested_proof']['revealed_attrs']:
                        self.log(
                            f"{attr_spec['name']}: "
                            f"{pres['requested_proof']['revealed_attrs'][referent]['raw']}"
                        )
                    else:
                        self.log(
                            f"{attr_spec['name']}: "
                            "(attribute not revealed)"
                        )
                for id_spec in pres["identifiers"]:
                    # just print out the schema/cred def id's of presented claims
                    self.log(f"schema_id: {id_spec['schema_id']}")
                    self.log(f"cred_def_id {id_spec['cred_def_id']}")
                # TODO placeholder for the next step
                await self.admin_POST(
                    f"/connections/{self.connection_id}/send-message", {"content": '1'}
                )
                log_status('#15 Query for credentials in the wallet that satisfy the proof request')
                log_status('#16 Generate the indy proof')
                log_status('#17 Send the proof to X: {"indy": {"requested_predicates": {}, "requested_attributes": {"0_id_uuid": {"cred_id": "cc5cb349-8312-46dc-8525-59f27782556d", "revealed": false}, "0_date_uuid": {"cred_id": "cc5cb349-8312-46dc-8525-59f27782556d", "revealed": true}, "0_branch_approval_uuid": {"cred_id": "cc5cb349-8312-46dc-8525-59f27782556d", "revealed": true}, "0_approved_entity_dateint_uuid": {"cred_id": "cc5cb349-8312-46dc-8525-59f27782556d", "revealed": true}, "0_mission_type_tasking_authorization_uuid": {"cred_id": "cc5cb349-8312-46dc-8525-59f27782556d", "revealed": true}}, "self_attested_attributes": {}}}')
                self.log('Presentation: state = presentation-sent, pres_ex_id = 3414902f-511e-4555-97f2-27b8d45e5d36')
                self.log('Presentation: state = done, pres_ex_id = 3414902f-511e-4555-97f2-27b8d45e5d36')

                await self.admin_POST(
                    f"/connections/{self.connection_id}/send-message", {"content": '2'}
                )
            else:
                # in case there are any other kinds of proofs received
                self.log("#13 Received ", pres_req["name"])
                

    async def handle_basicmessages(self, message):
        if ((message['content']) != '1' and (not('Mission Details:' in message['content'])) and ('alice.agent' not in message['content'])):
            log_status(message)
            self.log("Received message:", message["content"])
        elif (('Mission Details:' in message['content'])):
            log_status("#7 Request proof of certification from drone")
            req_attrs = [
                {
                    "name": "id",
                    "restrictions": [{"schema_name": "drone schema"}]
                },
                {
                    "name": "date",
                    "restrictions": [{"schema_name": "drone schema"}]
                },
                {
                    "name": "branch_approval",
                    "restrictions": [{"schema_name": "drone schema"}]
                },
                {
                    "name": "circulation_start_dateint",
                    "restrictions": [{"schema_name": "drone schema"}]
                },
                {
                    "name": "mission_type",
                    "restrictions": [{"schema_name": "drone schema"}]
                }
            ]
            req_preds = []
            indy_proof_request = {
                "name": "Proof of Certification",
                "version": "1.0",
                "nonce": str(uuid4().int),
                "requested_attributes": {
                    f"0_{req_attr['name']}_uuid": req_attr
                    for req_attr in req_attrs
                },
                "requested_predicates": {}
            }
            proof_request_web_request = {
                "connection_id": self.connection_id,
                "presentation_request": {"indy": indy_proof_request},
            }
            # this sends the request to our agent, which forwards it to Alice
            # (based on the connection_id)
            await self.admin_POST(
                "/present-proof-2.0/send-request",
                proof_request_web_request
            )
            self.set_mission_details(message["content"])
            self.set_mission_completed(True)


async def main(args):
    mission_completed = False
    acme_agent = await create_agent_with_args(args, ident="acme")


    try:
        log_status(
            "#1 Provision an agent and wallet, get back configuration details"
            + (
                f" (Wallet type: {acme_agent.wallet_type})"
                if acme_agent.wallet_type
                else ""
            )
        )
        agent = AcmeAgent(
            "acme.agent",
            acme_agent.start_port,
            acme_agent.start_port + 1,
            genesis_data=acme_agent.genesis_txns,
            genesis_txn_list=acme_agent.genesis_txn_list,
            no_auto=acme_agent.no_auto,
            tails_server_base_url=acme_agent.tails_server_base_url,
            timing=acme_agent.show_timing,
            multitenant=acme_agent.multitenant,
            mediation=acme_agent.mediation,
            wallet_type=acme_agent.wallet_type,
            seed=acme_agent.seed,
        )

        acme_agent.public_did = True
        acme_schema_name = "id schema"
        acme_schema_attrs = ["id", "name", "date", "position", "mission_type"]
        await acme_agent.initialize(
            the_agent=agent,
            schema_name=acme_schema_name,
            schema_attrs=acme_schema_attrs,
        )

        with log_timer("Publish schema and cred def duration:"):
        # define schema
            version = format(
                "%d.%d.%d"
                % (
                    random.randint(1, 101),
                    random.randint(1, 101),
                    random.randint(1, 101),
                )
            )
            # register schema and cred def
            (schema_id, cred_def_id) = await agent.register_schema_and_creddef(
                "id schema",
                version,
                ["id", "name", "date", "position", "mission_type"],
                support_revocation=False,
                revocation_registry_size=TAILS_FILE_COUNT,
            )

        # generate an invitation for Alice
        await acme_agent.generate_invitation(display_qr=True, wait=True)
        #await asyncio.sleep(5)
        log_status(agent.get_creds())
        await asyncio.sleep(1)
        mission_details = ''
        if(agent.get_creds()):
            options = (
                "    (1) Issue Credential\n"
                "    (2) Send Proof Request\n"
                "    (3) Send Task\n"
                "    (4) Request Mission Data\n"
                "    (X) Exit?\n"
                "[1/2/3/4/X]"
            )
        else:
            log_status("DRONE IS UNVERIFIABLE. EXIT THE CONNECTION")
            options = (
                "    (X) Exit?\n"
                "[X]"
            )
        async for option in prompt_loop(options):
            if option is not None:
                option = option.strip()

            if option is None or option in "xX":
                break

            elif option == "1":
                log_status("#13 Issue credential offer to X")
                agent.cred_attrs[cred_def_id] = {
                    "employee_id": "ACME0009",
                    "name": "Alice Smith",
                    "date": date.isoformat(date.today()),
                    "position": "CEO",
                    "mission_type": "Mine capture"
                }
                cred_preview = {
                    "@type": CRED_PREVIEW_TYPE,
                    "attributes": [
                        {"name": n, "value": v}
                        for (n, v) in agent.cred_attrs[cred_def_id].items()
                    ],
                }
                offer_request = {
                    "connection_id": agent.connection_id,
                    "comment": f"Offer on cred def id {cred_def_id}",
                    "credential_preview": cred_preview,
                    "filter": {"indy": {"cred_def_id": cred_def_id}},
                }
                await agent.admin_POST(
                    "/issue-credential-2.0/send-offer", offer_request
                )

            elif option == "2":
                log_status("#7 Request proof of certification from drone")
                req_attrs = [
                    {
                        "name": "id",
                        "restrictions": [{"schema_name": "drone schema"}]
                    },
                    {
                        "name": "date",
                        "restrictions": [{"schema_name": "drone schema"}]
                    },
                    {
                        "name": "branch_approval",
                        "restrictions": [{"schema_name": "drone schema"}]
                    },
                    {
                        "name": "circulation_start_dateint",
                        "restrictions": [{"schema_name": "drone schema"}]
                    },
                    {
                        "name": "mission_type",
                        "restrictions": [{"schema_name": "drone schema"}]
                    }
                ]
                req_preds = []
                indy_proof_request = {
                    "name": "Proof of Certification",
                    "version": "1.0",
                    "nonce": str(uuid4().int),
                    "requested_attributes": {
                        f"0_{req_attr['name']}_uuid": req_attr
                        for req_attr in req_attrs
                    },
                    "requested_predicates": {}
                }
                proof_request_web_request = {
                    "connection_id": agent.connection_id,
                    "presentation_request": {"indy": indy_proof_request},
                }
                # this sends the request to our agent, which forwards it to Alice
                # (based on the connection_id)
                await agent.admin_POST(
                    "/present-proof-2.0/send-request",
                    proof_request_web_request
                )

            elif option == "3":
                msg = await prompt("Enter task: ")
                await agent.admin_POST(
                    f"/connections/{agent.connection_id}/send-message", {"content": '3'}
                )

               # await agent.returnMission()
            elif option == "4":
                if not(agent.get_mission_completed()):
                    agent.log('No Mission Data')
                else:
                    detailList = (agent.get_mission_details()).split('\n')
                    for i in detailList:
                        agent.log(i.strip())
                
             

        if acme_agent.show_timing:
            timing = await acme_agent.agent.fetch_timing()
            if timing:
                for line in acme_agent.agent.format_timing(timing):
                    log_msg(line)

    finally:
        terminated = await acme_agent.terminate()

    await asyncio.sleep(0.1)

    if not terminated:
        os._exit(1)


if __name__ == "__main__":
    parser = arg_parser(ident="acme", port=8040)
    args = parser.parse_args()

    ENABLE_PYDEVD_PYCHARM = os.getenv("ENABLE_PYDEVD_PYCHARM", "").lower()
    ENABLE_PYDEVD_PYCHARM = ENABLE_PYDEVD_PYCHARM and ENABLE_PYDEVD_PYCHARM not in (
        "false",
        "0",
    )
    PYDEVD_PYCHARM_HOST = os.getenv("PYDEVD_PYCHARM_HOST", "localhost")
    PYDEVD_PYCHARM_CONTROLLER_PORT = int(
        os.getenv("PYDEVD_PYCHARM_CONTROLLER_PORT", 5001)
    )

    if ENABLE_PYDEVD_PYCHARM:
        try:
            import pydevd_pycharm

            print(
                "Acme remote debugging to "
                f"{PYDEVD_PYCHARM_HOST}:{PYDEVD_PYCHARM_CONTROLLER_PORT}"
            )
            pydevd_pycharm.settrace(
                host=PYDEVD_PYCHARM_HOST,
                port=PYDEVD_PYCHARM_CONTROLLER_PORT,
                stdoutToServer=True,
                stderrToServer=True,
                suspend=False,
            )
        except ImportError:
            print("pydevd_pycharm library was not found")

    check_requires(args)

    try:
        asyncio.get_event_loop().run_until_complete(main(args))
    except KeyboardInterrupt:
        os._exit(1)
