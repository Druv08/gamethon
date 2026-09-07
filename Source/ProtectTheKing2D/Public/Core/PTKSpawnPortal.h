// Protect the King - 2D. An outer-map region enemies arrive from.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "PTKSpawnPortal.generated.h"

/**
 * APTKSpawnPortal
 * ===============
 * One of the four corner regions on the map where a horde can appear.
 *
 * A portal is a PLACE, not a spawner: it knows where it is, what to call itself
 * and whether it is currently warning of an incoming horde. Deciding what to
 * spawn and when belongs to the wave manager, which is why that logic is not
 * here - four portals each running their own schedule could not produce the
 * "wave 3 is a mix arriving from two sides" behaviour the spec asks for.
 *
 * The warning state lives here rather than on the wave manager because it is
 * per-place information that both the minimap and the HUD read, and duplicating
 * "which corner is about to light up" into two systems is how the two end up
 * disagreeing.
 */
UCLASS()
class PROTECTTHEKING2D_API APTKSpawnPortal : public AActor
{
	GENERATED_BODY()

public:
	APTKSpawnPortal();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Stable id, e.g. "NorthWest". Used by logs and the minimap. */
	UFUNCTION(BlueprintPure, Category = "PTK|Portal")
	FName GetPortalId() const { return PortalId; }

	UFUNCTION(BlueprintPure, Category = "PTK|Portal")
	FText GetPortalDisplayName() const { return PortalDisplayName; }

	/** A point inside the spawn region, jittered so nothing stacks. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Portal")
	FVector PickSpawnPoint(FRandomStream& Stream) const;

	/** Lights the warning for Seconds. The horde itself arrives when it expires. */
	UFUNCTION(BlueprintCallable, Category = "PTK|Portal")
	void BeginWarning(float Seconds);

	UFUNCTION(BlueprintCallable, Category = "PTK|Portal")
	void ClearWarning();

	UFUNCTION(BlueprintPure, Category = "PTK|Portal")
	bool IsWarning() const { return WarningRemaining > 0.0f; }

	UFUNCTION(BlueprintPure, Category = "PTK|Portal")
	float GetWarningRemaining() const { return WarningRemaining; }

	UFUNCTION(BlueprintPure, Category = "PTK|Portal")
	float GetSpawnRadius() const { return SpawnRadius; }

protected:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Portal")
	FName PortalId = NAME_None;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Portal")
	FText PortalDisplayName;

	/**
	 * Radius of the region enemies appear inside.
	 *
	 * Generous on purpose: a whole horde arriving from one point spends its
	 * first second untangling itself instead of advancing.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Portal", meta = (ClampMin = "0.0"))
	float SpawnRadius = 220.0f;

	/** Nothing spawns nearer the portal centre than this, so arrivals fan out. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PTK|Portal", meta = (ClampMin = "0.0"))
	float MinSpawnRadius = 40.0f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category = "PTK|Portal")
	float WarningRemaining = 0.0f;
};
