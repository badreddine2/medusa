package cmd

import (
	"fmt"
	"io"
	"io/ioutil"
	"os"
	"path/filepath"
	"strings"

	"github.com/jonasvinther/medusa/pkg/encrypt"
	"github.com/jonasvinther/medusa/pkg/importer"
	"github.com/jonasvinther/medusa/pkg/vaultengine"

	"github.com/spf13/cobra"
)

func init() {
	rootCmd.AddCommand(importCmd)
	importCmd.PersistentFlags().BoolP("decrypt", "d", false, "Decrypt the Vault data before importing")
	importCmd.PersistentFlags().StringP("private-key", "p", "", "Location of the RSA private key")
	importCmd.PersistentFlags().StringP("engine-type", "m", "kv2", "Specify the secret engine type [kv1|kv2]")
}

var importCmd = &cobra.Command{
	Use:   "import [vault path] ['file1' 'file2' ... or '-' to read from stdin]",
	Short: "Import yaml/json files into a Vault instance",
	Long:  ``,
	Args:  cobra.MinimumNArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		path := args[0]
		inputPaths := args[1:] // Prendre tous les fichiers ou dossiers spécifiés
		vaultAddr, _ := cmd.Flags().GetString("address")
		vaultToken, _ := cmd.Flags().GetString("token")
		insecure, _ := cmd.Flags().GetBool("insecure")
		vaultRole, _ := cmd.Flags().GetString("role")
		kubernetes, _ := cmd.Flags().GetBool("kubernetes")
		authPath, _ := cmd.Flags().GetString("kubernetes-auth-path")
		namespace, _ := cmd.Flags().GetString("namespace")
		engineType, _ := cmd.Flags().GetString("engine-type")
		doDecrypt, _ := cmd.Flags().GetBool("decrypt")
		privateKey, _ := cmd.Flags().GetString("private-key")

		client := vaultengine.NewClient(vaultAddr, vaultToken, insecure, namespace, vaultRole, kubernetes, authPath)
		engine, prefix, err := client.MountpathSplitPrefix(path)
		if err != nil {
			fmt.Println(err)
			return err
		}

		client.UseEngine(engine)
		client.SetEngineType(engineType)

		for _, inputPath := range inputPaths {
			// Vérifiez si le chemin est un dossier
			if isDir(inputPath) {
				err := processDirectory(inputPath, func(filePath string) error {
					return processFile(filePath, cmd, client, prefix, doDecrypt, privateKey)
				})
				if err != nil {
					fmt.Printf("Erreur lors de l'importation du dossier %s: %v\n", inputPath, err)
				}
			} else {
				// Si c'est un fichier ou stdin
				err := processFile(inputPath, cmd, client, prefix, doDecrypt, privateKey)
				if err != nil {
					fmt.Printf("Erreur lors de l'importation du fichier %s: %v\n", inputPath, err)
				}
			}
		}

		return nil
	},
}

// Vérifie si un chemin est un dossier
func isDir(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return info.IsDir()
}

// Parcourt un dossier récursivement
func processDirectory(path string, fileHandler func(string) error) error {
	return filepath.Walk(path, func(filePath string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		// Ignorer les dossiers eux-mêmes
		if info.IsDir() {
			return nil
		}
		// Appeler la fonction de gestion des fichiers
		return fileHandler(filePath)
	})
}

// Gère un fichier individuel
func processFile(file string, cmd *cobra.Command, client *vaultengine.Client, prefix string, doDecrypt bool, privateKey string) error {
	var data []byte
	var err error

	if file == "-" {
		// Lire les données depuis stdin
		var inputReader io.Reader = cmd.InOrStdin()
		data, err = ioutil.ReadAll(inputReader)
		if err != nil {
			return fmt.Errorf("erreur lors de la lecture depuis stdin : %v", err)
		}
	} else {
		// Lire les données depuis le fichier
		data, err = importer.ReadFromFile(file)
		if err != nil {
			return fmt.Errorf("erreur lors de la lecture du fichier %s: %v", file, err)
		}
	}

	// Décryptage si nécessaire
	if doDecrypt {
		decryptedData, err := encrypt.Decrypt(privateKey, file)
		if err != nil {
			return fmt.Errorf("erreur lors du décryptage du fichier %s: %v", file, err)
		}
		data = []byte(decryptedData)
	}

	// Importer et parser les données
	parsedYaml, err := importer.Import(data)
	if err != nil {
		return fmt.Errorf("erreur lors de l'importation du fichier %s: %v", file, err)
	}

	// Écrire les données dans Vault
	for subPath, value := range parsedYaml {
		fullPath := prefix + strings.TrimPrefix(subPath, "/")
		client.SecretWrite(fullPath, value)
	}

	return nil
}
