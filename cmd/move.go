package cmd

import (
	"fmt"
	"io/ioutil"
	"strings"
	"github.com/spf13/cobra"
	"github.com/jonasvinther/medusa/pkg/vaultengine"
	"github.com/jonasvinther/medusa/pkg/importer"
	"github.com/manifoldco/promptui"
	//"github.com/jonasvinther/medusa/pkg/encrypt"
)

func init() {
	rootCmd.AddCommand(moveCmd)
	moveCmd.PersistentFlags().BoolP("auto-approve", "y", false, "Skip interactive approval of plan before deletion")
	moveCmd.PersistentFlags().StringP("engine-type", "m", "kv2", "Specify the secret engine type [kv1|kv2]")
}

var moveCmd = &cobra.Command{
	Use:   "move",
	Short: "Move Vault secret from one path to another",
	Long:  ``,
	Args:  cobra.MinimumNArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		sourcePath := args[0]
		targetPath := args[1]
		vaultAddr, _ := cmd.Flags().GetString("address")
		vaultToken, _ := cmd.Flags().GetString("token")
		vaultRole, _ := cmd.Flags().GetString("role")
		kubernetes, _ := cmd.Flags().GetBool("kubernetes")
		authPath, _ := cmd.Flags().GetString("kubernetes-auth-path")
		insecure, _ := cmd.Flags().GetBool("insecure")
		namespace, _ := cmd.Flags().GetString("namespace")
		engineType, _ := cmd.Flags().GetString("engine-type")
		isApproved, _ := cmd.Flags().GetBool("auto-approve")

		// Créer un client Vault
		client := vaultengine.NewClient(vaultAddr, vaultToken, insecure, namespace, vaultRole, kubernetes, authPath)

		// Splitting the path and determining engine type
		engine, sourcePath, err := client.MountpathSplitPrefix(sourcePath)
		if err != nil {
			fmt.Println("Erreur lors du split du chemin source:", err)
			return err
		}
		client.UseEngine(engine)
		client.SetEngineType(engineType)

		// Exporter le secret du chemin source
		exportData, err := client.FolderExport(sourcePath)
		if err != nil {
			fmt.Println("Erreur lors de l'export:", err)
			return err
		}

		// Si les données sont vides, lève une exception
		if len(exportData) == 0 {
			return fmt.Errorf("Aucune donnée trouvée dans le chemin source %s", sourcePath)
		}

		// Exporter les données dans un fichier temporaire (format YAML)
		tempFileName := "/tmp/exported_secret.yaml"
		data, err := vaultengine.ConvertToYaml(exportData)
		if err != nil {
			fmt.Println("Erreur lors de la conversion en YAML:", err)
			return err
		}

		err = ioutil.WriteFile(tempFileName, data, 0644)
		if err != nil {
			fmt.Println("Erreur lors de l'écriture du fichier:", err)
			return err
		}

		// Appel de la fonction extractYamlData pour modifier le fichier YAML
		// Passer le chemin du fichier exporté et le chemin à extraire (par exemple, sourcePath)
		sourcePath_edited := strings.TrimSuffix(sourcePath, "/")
		fmt.Println(sourcePath_edited)
		err = extractYamlData(tempFileName, sourcePath_edited)
		if err != nil {
			fmt.Println("Erreur lors de l'extraction des données YAML:", err)
			return err
		}

		// Lire le fichier modifié
		fileData, err := ioutil.ReadFile(tempFileName)
		if err != nil {
			fmt.Println("Erreur lors de la lecture du fichier exporté:", err)
			return err
		}

		// Importer les données modifiées
		parsedYaml, err := importer.Import(fileData)
		if err != nil {
			fmt.Println("Erreur lors de l'importation des données YAML:", err)
			return err
		}

		// Écrire les données dans le chemin cible dans Vault
		for subPath, value := range parsedYaml {
			fullPath := targetPath + subPath
			fmt.Println(fullPath)			
			client.SecretWrite(fullPath, value)
		}

		secretPaths, err := client.CollectPaths(sourcePath)
		if err != nil {
			return err
		}

		// Print a list of all the secrets that will be deleted
		for _, key := range secretPaths {
			fmt.Printf("Deleting secret [%s%s]\n", engine, key)
		}

		// Prompt for confirmation
		if !isApproved {
			prompt := promptui.Prompt{
				Label:     fmt.Sprintf("Do you want to delete the %d secrets listed above? Only 'y' will be accepted to approve.", len(secretPaths)),
				IsConfirm: true,
			}

			result, err := prompt.Run()

			if err != nil {
				fmt.Printf("Aborting. No secrets got deleted\n")
			}

			if result == "y" {
				isApproved = true
			}
		}

		// Perform deletion of the secrets
		if isApproved {
			for _, key := range secretPaths {
				client.SecretDelete(key)
			}
			fmt.Printf("The secrets has now been deleted\n")
		}

		return nil
		fmt.Printf("Le secret du chemin %s a été copié avec succès vers %s\n", sourcePath, targetPath)
		return nil
	},
}

