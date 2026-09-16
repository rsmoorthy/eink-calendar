-- .nvim.lua (project root)
vim.lsp.config("arduino_language_server", {
	cmd = {
		"arduino-language-server",
		"-fqbn",
		"esp32:esp32:esp32",
		"-cli-config",
		vim.fn.expand("~/.arduino15/arduino-cli.yaml"),
	},
})
