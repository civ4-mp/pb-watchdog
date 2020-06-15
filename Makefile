FOLDER=$(realpath .)
USER=$(shell whoami)
GROUP=$(USER)

SYSTEMD_INSTALL_DIR=/etc/systemd/system
SYSTEMCTL_BIN=$(shell which systemctl)
VENV_DIR=$(FOLDER)/venv

# To use subcommand output as file [ cat <(echo "Test") ]
SHELL=/bin/bash

################################################################


help:
	@echo -e "Common targets:\n" \
		"make run                 -- Start daemon. Quit with Ctl+C\n" \
		"make update              -- Update and re-install in virtualenv" \
		"make start|stop|reload   -- Control systemd service\n" \
		"make install_service     -- Install systemd service for automatic start\n" \
		"                            Service will be started as '${USER}:${GROUP}'\n" \
		"make uninstall_service   -- Uninstall systemd service\n" \
		"make log                 -- Show journalctl log\n" \
		"\n" \
		"make control_service_without_sudo -- Allow start, stop and reload without sudo\n" \
		"\n" \
		"" \

run: network_cap_info $(VENV_DIR)
	source ./venv/bin/activate && cd "$(VENV_DIR)" \
		&& python bin/civpb-watchdog --config $(VENV_DIR)/civpb-watchdog.toml \
		# && deactivate

venv: $(VENV_DIR)
	@echo "Init virtual environment and install program into."

update:
	@echo "Update installed program"
	git pull \
		&& source ./venv/bin/activate \
		&& pip install -e .

# Trigger installation in virtualenv
$(VENV_DIR):
	virtualenv venv
	source ./venv/bin/activate \
		&& pip install -e .

install_service: civpb-watchdog.service $(VENV_DIR) $(VENV_DIR)/civpb-watchdog.toml
	sudo cp "$(FOLDER)/$<" "$(SYSTEMD_INSTALL_DIR)/$<"
	sudo systemctl daemon-reload
	sudo systemctl enable $<
	@echo -e "Service enabled, but not started.\n" \
		"Call 'sudo systemctl start $<' to start service."

control_service_without_sudo: civpb-watchdog.sudoers
	sudo install -m 0440 "civpb-watchdog.sudoers" "/etc/sudoers.d/civpb-watchdog"

start: civpb-watchdog.service
	sudo systemctl start $<

stop: civpb-watchdog.service
	sudo systemctl stop $<

restart: civpb-watchdog.service
	sudo systemctl restart $<

log: civpb-watchdog.service
	journalctl -u $<

%.service: examples/%.service.template
	@echo "Create systemd service file for startup."
	sed -e "s#{USER}#$(USER)#g" \
		-e "s#{GROUP}#$(GROUP)#g" \
		-e "s#{VENV_DIR}#$(VENV_DIR)#g" \
		"$<" > "$@"

$(VENV_DIR)/%.toml: examples/%.toml
	cp "$<" "$@"

%.sudoers: examples/%.sudoers.template
	@echo "Create sudoers file for unit control (start stop restart)"
	sed -e "s#{GROUP}#$(GROUP)#g" \
		-e "s#{SYSTEMCTL_BIN}#$(SYSTEMCTL_BIN)#g" \
		"$<" > "$@"

network_cap_info:
	@/bin/echo -e "Note that called python binary needs network capabilinties.\n" \
		"Use\n\tmake install_service\n" \
		"to create service or\n" \
		"create local python binary with enough rights (security risk).\n" \
		"\trm $(shell basename "$(VENV_DIR)")/bin/python\n" \
		"\tcp python $(shell basename "$(VENV_DIR)")/bin/python\n" \
		"\tsudo setcap cap_net_raw=ep $(shell basename "$(VENV_DIR)")/bin/python \n" \
